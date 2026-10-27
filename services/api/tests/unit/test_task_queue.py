"""队列路由及执行隔离的配置约束。"""
from src.infrastructure.tasks.celery_app import celery_app, QUEUES


def test_each_workload_has_durable_queue_and_late_ack():
    assert len(set(QUEUES.values())) == 4
    assert {queue.name for queue in celery_app.conf.task_queues} == set(QUEUES.values())
    assert all(queue.durable for queue in celery_app.conf.task_queues)
    assert celery_app.conf.task_acks_late and celery_app.conf.task_reject_on_worker_lost
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.broker_transport_options['confirm_publish']
    assert celery_app.conf.accept_content == ['json']
    assert celery_app.conf.task_ignore_result


def test_publisher_routes_id_only_message_with_actual_kombu_sender(monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4
    from kombu import Connection
    from src.infrastructure.tasks.celery_app import publish
    monkeypatch.setattr(celery_app, 'connection_for_write', lambda: Connection('memory://'))
    message = SimpleNamespace(kind='parse', id=str(uuid4()))
    publish(message)
    with Connection('memory://') as connection:
        queue = celery_app.amqp.queues[QUEUES['parse']](connection)
        received = queue.get(no_ack=True)
        assert received.payload[0] == [message.id]
        assert received.payload[1] == {}
        assert received.properties['delivery_mode'] == 2
        assert received.delivery_info['routing_key'] == QUEUES['parse']
