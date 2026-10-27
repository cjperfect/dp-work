"""API 内只投递持久化消息，不执行耗时业务任务。"""
import asyncio
import logging
import time
from src.infrastructure.tasks import outbox
from src.infrastructure.tasks.celery_app import publish
from src.task_handlers import recover_pending

log = logging.getLogger(__name__)


async def dispatch_once(publisher=publish):
    """独立线程等待 Broker 确认，失败后保留消息。"""
    message = await outbox.claim()
    if message is None:
        return False
    try:
        await asyncio.to_thread(publisher, message)
    except Exception:
        await outbox.dispatched(message, error=True)
        log.warning('MQ 投递失败，消息已保留，稍后重试。')
    else:
        await outbox.dispatched(message)
    return True


async def worker():
    """多实例安全投递与旧任务恢复。"""
    last_recovery = 0
    while True:
        try:
            if time.monotonic() - last_recovery > 30:
                await recover_pending()
                last_recovery = time.monotonic()
            if await dispatch_once():
                continue
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning('MQ 投递器暂不可用，请检查数据库迁移。')
        await asyncio.sleep(1)
