"""请求与 MQ 消费共享的用户设备执行范围。"""
from contextvars import ContextVar
from contextlib import contextmanager

scope = ContextVar('sidecar_device_scope', default=(None, None))


@contextmanager
def execution_scope(owner, device=None):
    """切换执行范围，退出后恢复上一个上下文。"""
    token = scope.set((owner, device))
    try:
        yield
    finally:
        scope.reset(token)
