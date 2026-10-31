"""节点级恢复：配置校验、工具执行凭据和不确定副作用拦截。"""
import asyncio
import hashlib
import json
import sqlite3
from importlib.metadata import version
from contextlib import closing

from langchain.agents.middleware import AgentMiddleware
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.errors import GraphInterrupt
from .. import config
from ..providers.llm.schemas import ModelError

SERDE = JsonPlusSerializer()
READ_ONLY = {'ls', 'read_file', 'glob', 'grep', 'file_search', 'list_directory', 'search_knowledge',
             'feishu_search_documents', 'feishu_read_document'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def file(run_id, suffix):
    from uuid import UUID
    UUID(run_id)
    root = config.WORKSPACE_DIR.parent / 'data/agent-checkpoints'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / (run_id + suffix)
    if root.is_symlink() or path.is_symlink():
        raise ModelError('RECOVERY_INVALID', '执行检查点路径无效。')
    return path


def has_checkpoint(run_id):
    """只将已持久化图状态的任务标记为可恢复。"""
    path = file(run_id, '.sqlite3')
    if not path.exists() or not file(run_id, '.recovery.json').exists():
        return False
    try:
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
            return db.execute('SELECT 1 FROM checkpoints LIMIT 1').fetchone() is not None
    except sqlite3.DatabaseError:
        return False


def database(run_id):
    path = file(run_id, '.tools.sqlite3')
    db = sqlite3.connect(path, timeout=10)
    db.execute('PRAGMA synchronous=FULL')
    db.execute('CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, name TEXT NOT NULL, kind TEXT, result BLOB)')
    path.chmod(0o600)
    return db


def identity(body, settings, tools):
    from ..agents.context import system_prompt
    from ..tools.workspace import agent_workspace
    from ..tools.projects import project_workspace
    root = project_workspace(body.project_id, body.workspace_owner_id) if body.project_id else agent_workspace(body.agent_code)
    stats = root.stat()
    prompt = system_prompt(body.agent_code, {item.name for item in tools}, root if body.project_id else None)
    skills = agent_workspace(body.agent_code) / 'skills'
    manifests = {str(p.relative_to(skills)): hashlib.sha256(p.read_bytes()).hexdigest() for p in skills.rglob('*') if p.is_file() and not p.is_symlink()}
    return {'owner':body.workspace_owner_id, 'thread':body.thread_id, 'signature':digest({
        'version':1, 'framework':[version('deepagents'), version('langgraph')], 'prompt':prompt, 'model':settings.model, 'base_url':settings.base_url,
        'max_tokens':settings.max_tokens, 'limits':[config.AGENT_MAX_STEPS, config.AGENT_REPEAT_LIMIT, config.AGENT_TOOL_ERROR_LIMIT, config.AGENT_SANDBOX_IMAGE], 'root':str(root), 'identity':[stats.st_dev, stats.st_ino], 'skills':manifests})}


def prepare(body, settings, tools):
    """恢复必须使用同一账号、目录、模型、提示词和技能配置。"""
    from ..providers.local_settings import atomic
    path = file(body.run_id, '.recovery.json')
    current = identity(body, settings, tools)
    if body.checkpoint_resume:
        if not path.exists() or json.loads(path.read_text()) != current:
            raise ModelError('RECOVERY_CONFIG_CHANGED', '原任务的模型、提示词、技能或工作目录已变化，请恢复原配置，或发送新消息继续处理。')
        with closing(database(body.run_id)) as db:
            pending = db.execute('SELECT name FROM calls WHERE result IS NULL').fetchall()
        if any(name not in READ_ONLY for (name,) in pending):
            raise ModelError('RECOVERY_TOOL_UNCERTAIN', '中断时有工具操作结果未确认，已阻止自动重放。请检查实际文件或外部资源，再发送新消息继续处理。')
        validate_files(body)
    elif not path.exists():
        atomic(path, json.dumps(current).encode())


def validate_files(body):
    """已记录文件被外部修改或撤销后，不继续使用旧执行状态。"""
    from ..tools.file_snapshots import run_changes, store_root, read_state
    from ..tools.workspace import agent_workspace
    from ..tools.projects import project_workspace
    root = project_workspace(body.project_id, body.workspace_owner_id) if body.project_id else agent_workspace(body.agent_code)
    latest = {}
    for change in run_changes(body.workspace_owner_id, body.run_id):
        record_path = store_root(body.workspace_owner_id) / 'changes' / (change['id'] + '.json')
        record = json.loads(record_path.read_text())
        if record.get('undone'):
            raise ModelError('RECOVERY_FILES_CHANGED', '原任务的文件修改已撤销，请发送新消息重新核验后继续。')
        if 'relative' not in record or 'after' not in record:
            raise ModelError('RECOVERY_FILES_CHANGED', '原任务的文件状态无法确认，请发送新消息核验后继续。')
        latest[record['relative']] = record
    for relative, record in latest.items():
        if str(root) != record['root'] or read_state(root, relative) != record['after']:
            raise ModelError('RECOVERY_FILES_CHANGED', '原任务修改的文件已有后续变化，请发送新消息重新核验后继续。')


async def durable(function, *args):
    """取消时等待已经开始的凭据写入完成。"""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


class RecoveryMiddleware(AgentMiddleware):
    def __init__(self, run_id):
        self.run_id = run_id

    def claim(self, call):
        fingerprint = digest({'name':call['name'], 'args':call.get('args', {})})
        with closing(database(self.run_id)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT fingerprint,kind,result FROM calls WHERE id=?', (call['id'],)).fetchone()
            if old:
                if old[0] != fingerprint:
                    raise ModelError('RECOVERY_TOOL_CHANGED', '工具调用参数与已保存记录不一致，已阻止执行。')
                if old[2] is not None:
                    return SERDE.loads_typed((old[1], old[2]))
                if call['name'] not in READ_ONLY:
                    raise ModelError('RECOVERY_TOOL_UNCERTAIN', '工具结果未确认，已阻止重复执行。')
            else:
                db.execute('INSERT INTO calls VALUES(?,?,?,NULL,NULL)', (call['id'], fingerprint, call['name']))
        return None

    def commit(self, call_id, result):
        kind, data = SERDE.dumps_typed(result)
        with closing(database(self.run_id)) as db, db:
            db.execute('UPDATE calls SET kind=?,result=? WHERE id=?', (kind, data, call_id))

    def release_interrupt(self, call_id):
        with closing(database(self.run_id)) as db, db:
            db.execute('DELETE FROM calls WHERE id=? AND result IS NULL', (call_id,))

    async def awrap_tool_call(self, request, handler):
        """副作用前提交意图，返回图之前提交结果；重放时复用已保存结果。"""
        saved = await durable(self.claim, request.tool_call)
        if saved is not None:
            return saved
        try:
            result = await handler(request)
        except GraphInterrupt:
            # 审批暂停由原图的子检查点恢复，并未结束父 task 调用。
            await durable(self.release_interrupt, request.tool_call['id'])
            raise
        await durable(self.commit, request.tool_call['id'], result)
        return result
