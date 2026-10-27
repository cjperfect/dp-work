"""Deep Agents 本机命令执行：异步取消、超时和输出限制。"""
import asyncio
import os
from pathlib import Path
import shutil
import signal

import anyio
from deepagents.backends.protocol import ExecuteResponse


async def terminate_tree(process):
    """停止命令进程树，包括命令启动的后台子进程。"""
    if os.name == "nt":
        if process.returncode is None:
            killer = await asyncio.create_subprocess_exec("taskkill", "/PID", str(process.pid), "/T", "/F",
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await killer.wait()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            await asyncio.sleep(.05)
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    if process.returncode is None:
        try:
            process.kill()
        except (ProcessLookupError, PermissionError):
            pass
    await process.wait()


async def execute_command(workspace: Path, command: str, timeout: float, max_output_bytes: int, environment: dict[str, str]):
    """执行单次 Bash 命令，被取消时清理整个命令进程组。"""
    if not isinstance(command, str) or not command.strip() or len(command) > 16000:
        return ExecuteResponse(output="命令不能为空，最多 16000 字符。", exit_code=1)
    executable = shutil.which("bash")
    if not executable and Path("/bin/bash").is_file():
        executable = "/bin/bash"
    if not executable:
        return ExecuteResponse(output="本机未安装 Bash。Windows 可安装 Git Bash 并加入 PATH。", exit_code=1)
    process = await asyncio.create_subprocess_exec(executable, "--noprofile", "--norc", "-c", command,
        cwd=workspace, env=environment, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        start_new_session=os.name != "nt")
    output = bytearray()
    timed_out = truncated = False
    try:
        async with asyncio.timeout(timeout):
            while block := await process.stdout.read(4096):
                remaining = max_output_bytes - len(output)
                output.extend(block[:remaining])
                if len(block) > remaining:
                    truncated = True
                    break
            if not truncated:
                await process.wait()
    except TimeoutError:
        timed_out = True
    finally:
        with anyio.CancelScope(shield=True):
            await terminate_tree(process)
    text = output.decode("utf-8", errors="replace")
    if timed_out:
        text += f"\n命令超过 {timeout:g} 秒，已终止。"
    if truncated:
        text += "\n输出超过限制，命令已终止。"
    return ExecuteResponse(output=text, exit_code=124 if timed_out else process.returncode, truncated=truncated)
