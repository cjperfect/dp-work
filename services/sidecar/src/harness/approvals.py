"""工具审批的持久化检查点、暂停事件和恢复校验。"""
import asyncio
import logging
from dataclasses import dataclass
from weakref import WeakValueDictionary
from contextlib import asynccontextmanager

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from .. import config
from ..providers.llm.schemas import ModelError
from .tool_policy import needs_approval

GATED_TOOLS = {name: {"allowed_decisions": ["approve", "reject"], "when": needs_approval}
               for name in ("write_file", "edit_file", "execute", "feishu_create_document")}
LOCKS = WeakValueDictionary()
log = logging.getLogger(__name__)


@dataclass
class ApprovalCheckpoint:
    saver: AsyncSqliteSaver
    pending: bool = False


def remove_checkpoint(file):
    """已结束运行不保留重复历史，仅待审批运行持久化检查点。"""
    for suffix in ('', '-wal', '-shm'):
        try:
            file.with_name(file.name + suffix).unlink(missing_ok=True)
        except OSError:
            log.warning('无法清理 Agent 检查点 %s', file.name)


@asynccontextmanager
async def checkpoint(run_id):
    """按运行隔离检查点，进程重启后仍可恢复未执行的审批。"""
    root = config.WORKSPACE_DIR.parent / "data" / "agent-checkpoints"
    await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True, mode=0o700)
    lock = LOCKS.setdefault(run_id, asyncio.Lock())
    async with lock:
        file = root / f"{run_id}.sqlite3"
        state = None
        existed = await asyncio.to_thread(file.exists)
        try:
            async with AsyncSqliteSaver.from_conn_string(str(file)) as saver:
                state = ApprovalCheckpoint(saver, pending=existed)
                yield state
        finally:
            if state is not None and not state.pending:
                await asyncio.to_thread(remove_checkpoint, file)


async def resume_input(graph, run_config, decisions):
    """只接受当前检查点完整对应的一次性允许或拒绝。"""
    snapshot = await graph.aget_state(run_config)
    pending = snapshot.interrupts
    if not pending or set(decisions) != {item.id for item in pending}:
        raise ModelError("APPROVAL_STALE", "审批已失效或执行状态已变化，请重新加载。")
    for item in pending:
        actions = item.value.get("action_requests", [])
        answers = decisions[item.id].get("decisions", [])
        if not actions or len(answers) != len(actions) or any(answer.get("type") not in ("approve", "reject") for answer in answers):
            raise ModelError("APPROVAL_INVALID", "审批决定与待执行操作不一致。")
    return Command(resume=decisions)
