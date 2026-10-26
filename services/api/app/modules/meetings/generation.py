"""PostgreSQL 持久化任务与 Sidecar 调度。"""
import asyncio
import logging
from uuid import uuid4
import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func
from app.core import config
from app.core.exceptions import ApiError
from app.core.responses import ApiCode
from app.infrastructure.database import session
from .repository import MeetingsRepository
from .models import MeetingMinutes
from . import records
from .schemas import GenerateMinutes, GenerationAccepted, MeetingState
from .service import _workspace

log = logging.getLogger(__name__)
SAFE_ERRORS = {
    "MODEL_NOT_CONFIGURED": "请配置 Sidecar 的 ARK_API_KEY 和 ARK_MODEL。",
    "MODEL_AUTH_FAILED": "方舟 API Key 无效，或无权访问该模型。",
    "MODEL_RATE_LIMIT": "方舟模型请求限流，请稍后重试。",
    "MODEL_TIMEOUT": "方舟模型调用超时，请稍后重试。",
    "MEETING_TOO_LONG": "会议内容超过当前生成长度限制。",
    "MODEL_INCOMPLETE": "模型未返回完整纪要，请调整输出长度或重试。",
    "MINUTES_FORMAT_INVALID": "模型返回的纪要结构不完整，请重试。",
}


class GeneratedMinutes(BaseModel):
    task_id: str
    source_revision: int
    content: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)


async def enqueue(owner_id: int, meeting_id: str, body: GenerateMinutes) -> GenerationAccepted:
    """固定原始内容快照并提交生成任务，重复点击复用当前任务。"""
    async with session.transaction() as conn:
        repository = MeetingsRepository(conn)
        record = await repository.get(owner_id, meeting_id, lock=True)
        if record is None:
            raise ApiError(ApiCode.NOT_FOUND, "会议不存在", 404)
        if record.status != "ended":
            raise ApiError(ApiCode.STATE_CONFLICT, "请先结束会议，再生成会议纪要。", 409)
        active = await repository.active_job(meeting_id)
        if active:
            return GenerationAccepted(task_id=active.id, source_revision=active.source_revision, meeting=MeetingState.model_validate(record))
        if record.revision != body.expected_revision:
            raise ApiError(ApiCode.STATE_CONFLICT, "会议内容已变化，请重新加载后再生成。", 409)
        workspace = await _workspace(repository, record)
        segments = [row.model_dump() for row in workspace.segments]
        if not any(row["text"].strip() for row in segments):
            raise ApiError(ApiCode.STATE_CONFLICT, "没有可生成纪要的会议原始内容。", 409)
        task_id = str(uuid4())
        payload = {"task_id": task_id, "meeting_id": meeting_id, "source_revision": record.revision,
                   "title": record.title, "scheduled_at": workspace.meeting.scheduled_at.isoformat(),
                   "segments": segments}
        await repository.create_job(task_id, meeting_id, record.revision, payload)
        source_revision = record.revision
        record.generation_task_id = task_id
        record.generation_source_revision = source_revision
        record.generation_status = "generating"
        record.generation_error = None
        record.minutes_status = 0
        record.revision += 1
        record.updated_at = func.clock_timestamp()
        await conn.flush()
        await conn.refresh(record)
        await repository.notify_generation(owner_id, meeting_id)
        await records.notify(conn, meeting_id)
        return GenerationAccepted(task_id=task_id, source_revision=source_revision, meeting=MeetingState.model_validate(record))


async def call_sidecar(payload: dict, transport=None) -> GeneratedMinutes:
    """调用内部生成接口，不向浏览器暴露内部凭证或上游错误。"""
    if not config.SIDECAR_INTERNAL_TOKEN:
        raise ValueError("API 与 Sidecar 的内部服务凭证尚未配置。")
    try:
        async with asyncio.timeout(config.MINUTES_TASK_TIMEOUT):
            async with httpx.AsyncClient(timeout=config.MINUTES_TASK_TIMEOUT, transport=transport) as client:
                response = await client.post(config.SIDECAR_API_URL + "/internal/meetings/minutes/generate",
                    headers={"X-Internal-Token": config.SIDECAR_INTERNAL_TOKEN}, json=payload)
        try:
            response_body = response.json()
        except (ValueError, UnicodeDecodeError) as cause:
            raise ValueError("纪要生成服务未返回有效结果，请稍后重试。") from cause
        if response.status_code != 200:
            detail = response_body.get("detail") if isinstance(response_body, dict) else None
            code = detail.get("code") if isinstance(detail, dict) else None
            raise ValueError(SAFE_ERRORS.get(code, "纪要生成服务请求失败，请检查服务配置后重试。"))
        result = GeneratedMinutes.model_validate(response_body)
        if result.task_id != payload["task_id"] or result.source_revision != payload["source_revision"]:
            raise ValueError("生成服务返回了不匹配的内容版本。")
        if not result.content.strip():
            raise ValueError("模型未返回有效的会议纪要。")
        return result
    except (TimeoutError, httpx.TimeoutException) as cause:
        raise ValueError("会议纪要生成超时，请稍后重试。") from cause
    except (httpx.HTTPError, ValidationError) as cause:
        raise ValueError("会议纪要生成服务暂时不可用，请稍后重试。") from cause


async def finish(task_id: str, claim_token: str, result: GeneratedMinutes | None, error: str | None = None) -> None:
    """原子保存任务结果和纪要，过期批次与已删除会议不回写。"""
    async with session.transaction() as conn:
        repository = MeetingsRepository(conn)
        job = await repository.claimed_job(task_id, claim_token)
        if job is None:
            return
        meeting = await repository.job_meeting(job.meeting_id)
        if meeting is None or meeting.generation_task_id != task_id:
            job.status, job.error = "failed", "生成任务已失效。"
            return
        job.completed_at = func.now()
        job.lease_until = None
        job.error = error
        if result:
            minutes = await repository.minutes(meeting.id)
            if minutes is None:
                minutes = MeetingMinutes(meeting_id=meeting.id)
                conn.add(minutes)
            minutes.content, minutes.blocks, minutes.status = result.content, None, 1
            job.status, job.result = "succeeded", result.model_dump()
            meeting.generation_status, meeting.minutes_status = "ready", 1
            meeting.generation_error = None
        else:
            job.status = "failed"
            meeting.generation_status, meeting.generation_error = "failed", error or "纪要生成失败，请重试。"
            meeting.minutes_status = 1 if await repository.minutes(meeting.id) else None
        meeting.revision += 1
        meeting.updated_at = func.clock_timestamp()
        await conn.flush()
        await repository.notify_generation(meeting.owner_id, meeting.id)
        await records.notify(conn, meeting.id)


async def run_once(transport=None) -> bool:
    """领取并执行一个任务，模型调用期间不占用数据库事务。"""
    async with session.transaction() as conn:
        job = await MeetingsRepository(conn).claim_job(config.MINUTES_TASK_TIMEOUT + 60)
        if job is None:
            return False
        task_id, claim, payload, attempts = job.id, job.claim_token, job.input, job.attempts
    if attempts > 3:
        await finish(task_id, claim, None, "生成任务多次中断，请手动重新生成。")
        return True
    try:
        result = await call_sidecar(payload, transport)
    except asyncio.CancelledError:
        raise
    except ValueError as cause:
        await finish(task_id, claim, None, str(cause))
    except Exception:
        log.warning("会议纪要任务执行失败，task=%s", task_id)
        await finish(task_id, claim, None, "会议纪要生成失败，请稍后重试。")
    else:
        await finish(task_id, claim, result)
    return True


async def worker() -> None:
    """持续扫描持久化任务，重启后恢复排队和租约过期的任务。"""
    while True:
        try:
            if await run_once():
                continue
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("会议纪要任务扫描失败，请检查数据库和迁移。")
        await asyncio.sleep(1)
