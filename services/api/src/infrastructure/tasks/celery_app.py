"""Celery 配置；任务结果以 PG 业务表为准，无需 Redis。"""
from celery import Celery
from kombu import Exchange, Queue
from src.core import config

QUEUES = {
    'minutes': 'meeting-minutes',
    'parse': 'document-parse',
    'vector': 'document-vectorize',
    'search': 'search-sync',
}
exchange = Exchange('dp-work', type='direct', durable=True)
celery_app = Celery('dp-work', broker=config.MQ_BROKER_URL, include=['src.task_handlers'])
celery_app.conf.update(
    task_queues=[Queue(name, exchange=exchange, routing_key=name, durable=True) for name in QUEUES.values()],
    task_routes={f'dp_work.{kind}': {'queue': queue, 'routing_key': queue} for kind, queue in QUEUES.items()},
    task_create_missing_queues=False,
    task_default_queue=QUEUES["minutes"], task_default_exchange="dp-work",
    task_default_exchange_type="direct", task_default_routing_key=QUEUES["minutes"],
    task_serializer='json', accept_content=['json'], result_serializer='json',
    task_ignore_result=True, task_store_errors_even_if_ignored=False,
    task_default_delivery_mode='persistent', task_acks_late=True,
    task_reject_on_worker_lost=True, worker_prefetch_multiplier=1,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    broker_transport_options={'confirm_publish': True}, broker_connection_timeout=5,
    broker_connection_retry_on_startup=True, task_publish_retry=False,
    # solo 在主线程执行长任务，关闭 AMQP 心跳，避免执行期间被误判断线。
    broker_heartbeat=0 if config.MQ_WORKER_POOL == "solo" else 60,
    task_time_limit=config.MQ_TASK_TIME_LIMIT,
    worker_max_tasks_per_child=100, timezone='UTC', enable_utc=True,
    worker_hijack_root_logger=False,
)


def publish(message):
    """等待 Broker 确认后返回；不在 API 事件循环内调用。"""
    queue = QUEUES[message.kind]
    with celery_app.connection_for_write() as connection:
        connection.ensure_connection(max_retries=0)
        with celery_app.amqp.Producer(connection) as producer:
            celery_app.send_task(f'dp_work.{message.kind}', args=[message.id], task_id=message.id,
                queue=queue, routing_key=queue, producer=producer, retry=False,
                delivery_mode=2, confirm_timeout=5)
