"""工具审批的持久化检查点、暂停事件和恢复校验。"""
import asyncio
from contextlib import asynccontextmanager

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from .. import config
from ..providers.llm.schemas import ModelError

GATED_TOOLS = {name: {"allowed_decisions": ["approve", "reject"]}
               for name in ("write_file", "edit_file", "execute")}
LOCKS = {}


@asynccontextmanager
async def checkpoint(run_id):
    """按运行隔离检查点，进程重启后仍可恢复未执行的审批。"""
    root = config.WORKSPACE_DIR.parent / "data" / "agent-checkpoints"
    await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True, mode=0o700)
    async with LOCKS.setdefault(run_id, asyncio.Lock()):
        async with AsyncSqliteSaver.from_conn_string(str(root / f"{run_id}.sqlite3")) as saver:
            yield saver


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
