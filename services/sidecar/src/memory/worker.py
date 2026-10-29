"""Sidecar 生命周期内单并发后台生成，任务与进度保存在本机。"""
import asyncio
import logging
import sqlite3
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from .. import config
from ..providers import local_settings
from ..providers.llm.schemas import ModelSettings
from ..sessions.storage import storage, SessionError
from . import jobs, pipeline, repository as repo

log = logging.getLogger(__name__)


def candidates(root):
    """扫描轻量会话元数据，不把所有聊天正文载入内存。"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.MEMORY_IDLE_HOURS)
    oldest = datetime.now(timezone.utc) - timedelta(days=config.MEMORY_MAX_AGE_DAYS)
    result = []
    for file in sorted((root / 'data/users').glob('*/state.sqlite3')):
        if not file.parent.name.isdigit() or file.is_symlink() or file.parent.is_symlink():
            continue
        owner = int(file.parent.name)
        if owner <= 0:
            continue
        try:
            progress = {}
            memory_file = repo.memory_file(owner, root)
            if memory_file.exists() and not memory_file.is_symlink():
                memory_db = sqlite3.connect(f'file:{memory_file}?mode=ro', uri=True, timeout=2)
                memory_db.row_factory = sqlite3.Row
                try:
                    if not memory_db.execute('SELECT auto_generate FROM preferences WHERE id=1').fetchone()[0]:
                        continue
                    progress = {row['thread_id']: dict(row) for row in memory_db.execute('SELECT * FROM memory_jobs')}
                except sqlite3.OperationalError:
                    pass  # 旧版数据库先让 prepare 执行迁移。
                finally:
                    memory_db.close()
            db = sqlite3.connect(f'file:{file}?mode=ro', uri=True, timeout=2)
            try:
                for key, updated in db.execute('SELECT id,updated_at FROM threads WHERE deleted=0 AND has_history=1 ORDER BY updated_at DESC,id'):
                    try:
                        stamp = datetime.fromisoformat(updated)
                    except (ValueError, TypeError):
                        continue
                    job = progress.get(key)
                    if job:
                        if job['status'] == 'running' and job['lease_until'] > time.time():
                            continue
                        if job.get('source_updated') == updated and (job['status'] == 'done' or (job['status'] == 'retry' and (job['attempts'] >= jobs.MAX_ATTEMPTS or job['retry_at'] > time.time()))):
                            continue
                    if stamp.tzinfo and oldest <= stamp <= cutoff:
                        result.append((owner, key))
            finally:
                db.close()
        except (sqlite3.DatabaseError, ValueError, OSError):
            log.warning('Memory scan skipped an unavailable account store')
    return result


class MemoryWorker:
    def __init__(self, session_store=None):
        self.storage = session_store or storage
        self.task = None
        self.pass_lock = asyncio.Lock()

    def start(self):
        """只在有本机后台能力的 Sidecar 进程启动。"""
        if self.task is None:
            self.task = asyncio.create_task(self.run(), name='local-memory-worker')

    async def close(self):
        """退出时取消模型请求，已领取任务释放为可重试状态。"""
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    async def run(self):
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # 不输出模型响应、聊天或密钥。
                log.warning('Local memory background pass failed')
            await asyncio.sleep(config.MEMORY_SCAN_SECONDS)

    def prepare(self, owner, key):
        """会话锁始终先于记忆锁，与聊天上下文装配保持一致。"""
        with self.storage.lock:
            state = self.storage.get(owner, key)
            cutoff = datetime.now(timezone.utc) - timedelta(hours=config.MEMORY_IDLE_HOURS)
            stamp = datetime.fromisoformat(state['thread']['updated_at'])
            if not stamp.tzinfo or stamp > cutoff:
                return None
            return jobs.prepare(owner, state, self.storage.root)

    def apply(self, owner, job, extracted, decisions, known):
        """重新读取原分支和项目，防止模型生成期间用户继续工作。"""
        with self.storage.lock:
            state = self.storage.get(owner, job['thread_id'])
            project = state['thread'].get('project_id')
            if project:
                from ..tools.projects import project_workspace
                project_workspace(project, owner)
            return jobs.commit(owner, job, state, extracted, decisions, known, self.storage.root)

    async def process(self, job):
        owner, root = job['owner'], self.storage.root
        try:
            snapshot = job['snapshot']
            # 短会话与问候不调用模型；仍记录输入摘要，避免重复扫描。
            messages = snapshot['messages']
            meaningful = any(row['role'] == 'user' and len(row['text'].strip()) >= 12 for row in messages)
            extracted, decisions, known = [], [], []
            if meaningful and sum(len(row['text']) for row in messages) >= 80:
                runtime = await asyncio.to_thread(local_settings.runtime, owner, 'model')
                settings = runtime.llm() if runtime else ModelSettings.from_env()
                settings = replace(settings, timeout=min(settings.timeout, 60), max_tokens=3000)
                async with asyncio.timeout(135):
                    extracted = await pipeline.extract(snapshot, replace(settings, model=config.MEMORY_EXTRACT_MODEL or settings.model))
                    if extracted:
                        known = await asyncio.to_thread(jobs.existing, owner, snapshot, extracted, root)
                        decisions = await pipeline.consolidate(extracted, known, replace(settings, model=config.MEMORY_CONSOLIDATION_MODEL or settings.model))
            committed = await asyncio.to_thread(self.apply, owner, job, extracted, decisions, known)
            if not committed:
                await asyncio.to_thread(jobs.fail, owner, job, 'INPUT_CHANGED', root, True)
            else:
                from .vectors import backfill
                await backfill(owner, root)
        except asyncio.CancelledError:
            # 短本地事务等待完成后再退出，避免关闭后仍在后台写入。
            await asyncio.to_thread(jobs.fail, owner, job, 'CANCELLED', root, True)
            raise
        except Exception as cause:
            code = getattr(cause, 'code', None)
            code = code if code in ('MODEL_NOT_CONFIGURED', 'MODEL_AUTH_FAILED', 'MODEL_RATE_LIMIT', 'MODEL_TIMEOUT', 'MODEL_UNAVAILABLE') else 'MEMORY_GENERATION_FAILED'
            await asyncio.to_thread(jobs.fail, owner, job, code, root)
            log.warning('Local memory generation deferred (%s)', code)

    async def run_once(self):
        """每批最多处理配置数量；SQLite 领取保证多进程不会重复处理。"""
        async with self.pass_lock:
            from .vectors import backfill
            for directory in sorted((self.storage.root / 'memories').glob('*')):
                if directory.name.isdigit() and int(directory.name) > 0 and not directory.is_symlink():
                    await backfill(int(directory.name), self.storage.root)
            if not config.MEMORY_AUTO_ENABLED:
                return 0
            processed = 0
            for owner, key in await asyncio.to_thread(candidates, self.storage.root):
                if processed >= config.MEMORY_BATCH_SIZE:
                    break
                try:
                    job = await asyncio.to_thread(self.prepare, owner, key)
                except (repo.MemoryError, SessionError, ValueError, sqlite3.DatabaseError, OSError):
                    log.warning('Local memory candidate unavailable')
                    continue
                if job:
                    processed += 1
                    await self.process(job)
            return processed
