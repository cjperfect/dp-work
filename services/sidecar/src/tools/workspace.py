"""每个 Agent 独立的 Deep Agents 本机 Backend。"""
import asyncio
import os
from pathlib import Path
import re
from uuid import uuid4

from deepagents.backends import LocalShellBackend, CompositeBackend, FilesystemBackend

from .. import config
from .shell import execute_command
from .file_changes import emit_change
from .file_snapshots import SnapshotBatch, SnapshotError, workspace_lock


def finish_snapshot(batch):
    """后置扫描失败只报告实际限制，不能把已执行命令误报成尚未执行。"""
    try:
        return batch.finish()
    except (SnapshotError, OSError) as cause:
        return [{'id': str(uuid4()), 'path': str(batch.root), 'lines': [], 'additions': 0, 'deletions': 0,
                 'undoable': False, 'unavailable': '操作已执行，但部分变更扫描失败：' + str(cause) + '。请勿为获取 Diff 重复执行命令。'}]


def agent_workspace(agent_code: str) -> Path:
    """创建并校验 Agent 独立工作目录。"""
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", agent_code):
        raise ValueError("Agent 标识无效。")
    root = config.WORKSPACE_DIR
    workspace = root / agent_code
    if root.is_symlink() or workspace.is_symlink():
        raise ValueError("工作目录不能使用符号链接。")
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    return workspace.resolve()


class WorkspaceBackend(LocalShellBackend):
    """复用 Deep Agents 文件工具，命令执行支持异步取消。"""
    def _resolve_path(self, key: str) -> Path:
        """将工作目录内的真实绝对路径转换为工具虚拟路径。"""
        if self.virtual_mode and ".." not in key:
            try:
                relative = Path(key).relative_to(self.cwd)
            except ValueError:
                pass
            else:
                key = '/' + relative.as_posix()
        return super()._resolve_path(key)

    def execute(self, command: str, *, timeout: int | None = None):
        return asyncio.run(self.aexecute(command, timeout=timeout))

    def write(self, file_path: str, content: str):
        path = self._resolve_path(file_path)
        with workspace_lock(self.cwd):
            batch = SnapshotBatch(self.cwd, getattr(self, '_snapshot_owner', 0), [path.relative_to(self.cwd).as_posix()], getattr(self, '_snapshot_run', None))
            result = super().write(file_path, content)
            for change in finish_snapshot(batch):
                emit_change(change)
            return result

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False):
        path = self._resolve_path(file_path)
        with workspace_lock(self.cwd):
            batch = SnapshotBatch(self.cwd, getattr(self, '_snapshot_owner', 0), [path.relative_to(self.cwd).as_posix()], getattr(self, '_snapshot_run', None))
            result = super().edit(file_path, old_string, new_string, replace_all)
            for change in finish_snapshot(batch):
                emit_change(change)
            return result

    async def aexecute(self, command: str, *, timeout: int | None = None):
        effective_timeout = min(timeout if timeout is not None else self._default_timeout, self._default_timeout)
        if effective_timeout <= 0:
            raise ValueError("命令超时必须大于 0。")
        from ..harness.tool_policy import dangerous_command
        if not dangerous_command(command):
            return await execute_command(self.cwd, command, effective_timeout, self._max_output_bytes, self._env)
        from deepagents.backends.protocol import ExecuteResponse
        lock = workspace_lock(self.cwd)
        while not lock.acquire(blocking=False):
            await asyncio.sleep(.05)
        batch = None
        try:
            task = asyncio.create_task(asyncio.to_thread(SnapshotBatch, self.cwd, getattr(self, '_snapshot_owner', 0), None, getattr(self, '_snapshot_run', None)))
            try:
                batch = await asyncio.shield(task)
            except asyncio.CancelledError:
                await task
                raise
            return await execute_command(self.cwd, command, effective_timeout, self._max_output_bytes, self._env)
        except (SnapshotError, OSError) as cause:
            return ExecuteResponse(output=str(cause), exit_code=126)
        finally:
            try:
                if batch is not None:
                    task = asyncio.create_task(asyncio.to_thread(finish_snapshot, batch))
                    try:
                        changes = await asyncio.shield(task)
                    except asyncio.CancelledError:
                        changes = await task
                        for change in changes:
                            emit_change(change)
                        raise
                    for change in changes:
                        emit_change(change)
            finally:
                lock.release()


def agent_backend(agent_code: str, project_id: str | None = None, owner: int | None = None, run_id=None):
    """所有 Agent 默认绑定独立目录及相同的文件和命令能力。"""
    allowed = {"PATH", "HOME", "USER", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL", "SYSTEMROOT", "WINDIR", "COMSPEC"}
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    root = agent_workspace(agent_code)
    if project_id:
        from .projects import project_workspace
        root = project_workspace(project_id, owner)
    backend = WorkspaceBackend(root_dir=root, virtual_mode=True,
        timeout=30, max_output_bytes=32768, env=environment, inherit_env=False)
    backend._snapshot_owner = owner or 0
    backend._snapshot_run = run_id
    if not project_id:
        return backend
    skills = agent_workspace(agent_code) / "skills"
    skills.mkdir(exist_ok=True)
    return CompositeBackend(default=backend, routes={"/__agent_skills__/": FilesystemBackend(root_dir=skills, virtual_mode=True)})
