"""每个 Agent 独立的 Deep Agents 本机 Backend。"""
import asyncio
import os
from pathlib import Path
import re

from deepagents.backends import LocalShellBackend

from .. import config
from .shell import execute_command


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
    def execute(self, command: str, *, timeout: int | None = None):
        return asyncio.run(self.aexecute(command, timeout=timeout))

    async def aexecute(self, command: str, *, timeout: int | None = None):
        effective_timeout = min(timeout if timeout is not None else self._default_timeout, self._default_timeout)
        if effective_timeout <= 0:
            raise ValueError("命令超时必须大于 0。")
        return await execute_command(self.cwd, command, effective_timeout, self._max_output_bytes, self._env)


def agent_backend(agent_code: str):
    """所有 Agent 默认绑定独立目录及相同的文件和命令能力。"""
    allowed = {"PATH", "HOME", "USER", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL", "SYSTEMROOT", "WINDIR", "COMSPEC"}
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    return WorkspaceBackend(root_dir=agent_workspace(agent_code), virtual_mode=True,
        timeout=30, max_output_bytes=32768, env=environment, inherit_env=False)
