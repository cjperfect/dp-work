"""仅桌面托管模式检查父进程，避免 Electron 被强制终止后遗留服务。"""
import asyncio
import os
import signal


def parent_alive(pid: int):
    """检查指定父进程，兼容打包程序额外的启动进程。"""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5
        try:
            return kernel.WaitForSingleObject(handle, 0) != 0
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


async def watch_parent(parent_pid: int, interval: float = 2):
    """父进程消失后请求 Uvicorn 正常退出；手动启动不启用。"""
    if parent_pid <= 1:
        return
    while True:
        await asyncio.sleep(interval)
        if not parent_alive(parent_pid):
            os.kill(os.getpid(), signal.SIGTERM)
            return
