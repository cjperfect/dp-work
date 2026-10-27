"""启动四组独立 Worker，按队列分别限制并发。"""
import os
import signal
import subprocess
import sys
from src.core import config
from .celery_app import QUEUES


def main():
    """父进程退出时通知所有 Worker 优雅关闭。"""
    concurrency = {'minutes': config.MQ_MINUTES_CONCURRENCY, 'parse': config.MQ_PARSE_CONCURRENCY,
        'vector': config.MQ_VECTOR_CONCURRENCY, 'search': config.MQ_SEARCH_CONCURRENCY}
    if any(value < 1 or value > 64 for value in concurrency.values()):
        raise SystemExit('Worker 并发数必须为 1 至 64。')
    if config.MQ_WORKER_POOL not in ('solo', 'prefork'):
        raise SystemExit('MQ_WORKER_POOL 仅支持 solo / prefork。')
    processes = []
    stopping = False
    def stop(*_):
        nonlocal stopping
        stopping = True
        for process in processes:
            if process.poll() is None:
                process.terminate()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        for kind, queue in QUEUES.items():
            count = concurrency[kind] if config.MQ_WORKER_POOL == 'solo' else 1
            slots = 1 if config.MQ_WORKER_POOL == 'solo' else concurrency[kind]
            for index in range(count):
                processes.append(subprocess.Popen([sys.executable, '-m', 'celery', '-A',
                    'src.infrastructure.tasks.celery_app:celery_app', 'worker', '--loglevel=INFO',
                    '--queues=' + queue, '--hostname=' + f'{kind}-{index}@%h', '--concurrency=' + str(slots),
                    '--pool=' + config.MQ_WORKER_POOL,
                    '--without-gossip', '--without-mingle', '--without-heartbeat'],
                    env={**os.environ, 'PYTHONUNBUFFERED': '1'}))
        while not stopping:
            for process in processes:
                try:
                    status = process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    continue
                if stopping:
                    break
                raise SystemExit(status or 1)
    finally:
        stop()
        for process in processes:
            process.wait()


if __name__ == '__main__':
    main()
