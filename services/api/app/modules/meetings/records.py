"""富文本纪要的 CRDT 合并、分享和版本恢复。"""
import base64
import json
import secrets
from datetime import datetime, timezone
from uuid import uuid4
from pycrdt import Doc
from sqlalchemy import select, func, text
from app.core.exceptions import ApiError
from app.core.responses import ApiCode
from app.infrastructure.database import session
from app.modules.users.models import User
from .models import Meeting, MeetingMinutes
from .rich_text import state_from_minutes, minutes_from_state
from .record_models import MeetingRecord, MeetingRecordVersion

MAX_STATE = 4 * 1024 * 1024


def conflict(message):
    return ApiError(ApiCode.STATE_CONFLICT, message, 409)


async def access(db, meeting_id, user_id, share=None, owner_only=False):
    """锁定会议并校验所有者或登录后的分享权限。"""
    meeting = await db.scalar(select(Meeting).where(Meeting.id == meeting_id).with_for_update())
    record = await db.get(MeetingRecord, meeting_id)
    owner = meeting is not None and meeting.owner_id == user_id
    shared = record is not None and record.kind == "minutes" and share and record.share_token and secrets.compare_digest(share, record.share_token)
    if meeting is None or not (owner or (shared and not owner_only)):
        raise ApiError(ApiCode.NOT_FOUND, '会议不存在或无权访问', 404)
    return meeting, record


def editable(meeting):
    """仅允许协作编辑生成成功、尚未归档的纪要。"""
    return meeting.status == 'ended' and meeting.generation_status == 'ready'


def snapshot(db, record, author_id, label):
    """保存独立不可变的完整版本。"""
    item = MeetingRecordVersion(id=str(uuid4()), meeting_id=record.meeting_id, state=record.state,
        revision=record.revision, label=label, author_id=author_id, kind=record.kind)
    db.add(item)
    return item


async def notify(db, meeting_id):
    """通过 PostgreSQL 通知所有 API 进程中的协作者。"""
    await db.execute(text("SELECT pg_notify('meeting_record', :payload)"), {'payload': json.dumps({'id': meeting_id})})


def output(meeting, record, user_id):
    return {'meeting_id': meeting.id, 'title': meeting.title, 'owner': meeting.owner_id == user_id,
        'editable': editable(meeting), 'state': base64.b64encode(record.state).decode(),
        'content': minutes_from_state(record.state)[0],
        'epoch': record.epoch, 'revision': record.revision,
        'saved_revision': record.saved_revision, 'saved_at': record.saved_at.isoformat(), 'updated_at': record.updated_at.isoformat()}


async def get_document(meeting_id, user_id, share=None):
    """首次访问创建文档，以后读取同一协作状态。"""
    async with session.transaction() as db:
        meeting, record = await access(db, meeting_id, user_id, share)
        if meeting.generation_status != 'ready':
            raise conflict('会议纪要尚未生成，原始转写不支持协同。')
        if record is None or record.kind != 'minutes':
            minutes = await db.get(MeetingMinutes, meeting_id)
            if minutes is None:
                raise conflict('会议纪要不存在。')
            state = state_from_minutes(minutes.content, minutes.blocks)
            if record is None:
                record = MeetingRecord(meeting_id=meeting_id, state=state, epoch=str(uuid4()), revision=1, kind='minutes')
                db.add(record)
            else:
                snapshot(db, record, user_id, '旧原文协作备份')
                record.state, record.epoch, record.revision = state, str(uuid4()), 1
                record.share_token, record.kind = None, 'minutes'
                record.saved_revision, record.saved_at = 1, datetime.now(timezone.utc)
                record.updated_at = datetime.now(timezone.utc)
            snapshot(db, record, user_id, '生成纪要')
            await db.flush()
            await db.refresh(record)
        return output(meeting, record, user_id)


async def update_document(meeting_id, user_id, epoch, update, share=None):
    """在行锁内合并增量，提交成功后才通知其他客户端。"""
    if len(update) > MAX_STATE:
        raise conflict('本次修改过大，请拆分内容。')
    async with session.transaction() as db:
        meeting, record = await access(db, meeting_id, user_id, share)
        if record is None or record.kind != "minutes" or record.epoch != epoch:
            raise conflict('文档已恢复历史版本，请重新加载；未同步内容请先复制保留。')
        if not editable(meeting):
            raise conflict('当前会议纪要已锁定，不能修改。')
        doc = Doc()
        doc.apply_update(record.state)
        try:
            doc.apply_update(update)
            state = doc.get_update()
            if len(state) > MAX_STATE:
                raise ValueError('too large')
        except Exception as cause:
            raise conflict('无法保存本次富文本修改。') from cause
        if state != record.state:
            record.state, record.revision = state, record.revision + 1
            record.updated_at = datetime.now(timezone.utc)
            await db.flush()
            await notify(db, meeting_id)
        return output(meeting, record, user_id)


async def share_document(meeting_id, user_id):
    """由创建者生成可供登录同事协同编辑的稳定链接。"""
    await get_document(meeting_id, user_id)
    async with session.transaction() as db:
        meeting, record = await access(db, meeting_id, user_id, owner_only=True)
        if meeting.generation_status != 'ready':
            raise conflict('会议纪要尚未生成。')
        if not record.share_token:
            record.share_token = secrets.token_urlsafe(32)
        return {'token': record.share_token}


async def resolve_share(token, user_id):
    """登录后通过分享凭证查找协作文档。"""
    async with session.read_session() as db:
        record = await db.scalar(select(MeetingRecord).where(MeetingRecord.share_token == token))
        if record is None:
            raise ApiError(ApiCode.NOT_FOUND, '分享链接无效', 404)
        meeting_id = record.meeting_id
    return await get_document(meeting_id, user_id, token)


async def list_versions(meeting_id, user_id, share=None):
    """列出版本时间、作者和说明，不返回全部正文。"""
    async with session.transaction() as db:
        await access(db, meeting_id, user_id, share)
        rows = (await db.execute(select(MeetingRecordVersion, User.username).join(User, User.id == MeetingRecordVersion.author_id)
            .where(MeetingRecordVersion.meeting_id == meeting_id, MeetingRecordVersion.kind == "minutes").order_by(MeetingRecordVersion.created_at.desc()).limit(100))).all()
        return [{'id': row.id, 'revision': row.revision, 'label': row.label, 'author': name, 'created_at': row.created_at.isoformat()} for row, name in rows]


async def checkpoint(meeting_id, user_id, label):
    """保存一个有名称的历史版本。"""
    async with session.transaction() as db:
        meeting, record = await access(db, meeting_id, user_id, owner_only=True)
        if not record or not editable(meeting):
            raise conflict('当前不能保存版本。')
        snapshot(db, record, user_id, label.strip() or '手动版本')


async def version_state(meeting_id, user_id, version_id, share=None):
    """读取单个历史版本用于只读预览。"""
    async with session.transaction() as db:
        await access(db, meeting_id, user_id, share)
        version = await db.get(MeetingRecordVersion, version_id)
        if version is None or version.meeting_id != meeting_id or version.kind != "minutes":
            raise ApiError(ApiCode.NOT_FOUND, '版本不存在', 404)
        return {'state': base64.b64encode(version.state).decode()}


async def restore(meeting_id, user_id, version_id, expected_revision):
    """保存恢复前内容，再建立新的协作世代和恢复版本。"""
    async with session.transaction() as db:
        meeting, record = await access(db, meeting_id, user_id, owner_only=True)
        version = await db.get(MeetingRecordVersion, version_id)
        if record is None or version is None or version.meeting_id != meeting_id or version.kind != "minutes":
            raise ApiError(ApiCode.NOT_FOUND, '版本不存在', 404)
        if not editable(meeting) or record.revision != expected_revision:
            raise conflict('文档已变化，请读取最新内容后再恢复。')
        snapshot(db, record, user_id, '恢复前自动备份')
        record.state, record.epoch = version.state, str(uuid4())
        record.revision += 1
        record.updated_at = datetime.now(timezone.utc)
        snapshot(db, record, user_id, f'恢复版本：{version.label}')
        await sync_minutes(db, meeting, record)
        await db.flush()
        await notify(db, meeting_id)
        return output(meeting, record, user_id)


async def sync_minutes(db, meeting, record):
    """将已合并的协作状态同步为会议正文，供查询和归档读取。"""
    minutes = await db.get(MeetingMinutes, meeting.id)
    if minutes is None:
        minutes = MeetingMinutes(meeting_id=meeting.id, status=1, content='')
        db.add(minutes)
    minutes.content, minutes.blocks = minutes_from_state(record.state)
    record.saved_revision = record.revision
    record.saved_at = datetime.now(timezone.utc)
    meeting.revision += 1
    meeting.updated_at = record.saved_at


async def archive_minutes(meeting_id, user_id, base_id):
    """同一事务中归档最新协作纪要并锁定会议。"""
    from app.modules.knowledge import service as knowledge_service
    from app.modules.knowledge.schemas import KnowledgeDocumentSave
    from .repository import MeetingsRepository
    from .service import _workspace
    async with session.transaction() as db:
        meeting, record = await access(db, meeting_id, user_id, owner_only=True)
        if not editable(meeting):
            raise conflict('只有已生成且未归档的会议纪要可以归档。')
        if record and record.kind == 'minutes':
            await sync_minutes(db, meeting, record)
            snapshot(db, record, user_id, '归档版本')
        minutes = await db.get(MeetingMinutes, meeting_id)
        if not minutes or not minutes.content.strip():
            raise conflict('会议纪要为空，无法归档。')
        document_id = f'meeting-{meeting_id}'
        document = await knowledge_service.save_document_in_transaction(db, user_id, base_id, document_id, KnowledgeDocumentSave(title=meeting.title, content=minutes.content, blocks=minutes.blocks))
        if document is None:
            raise conflict('无法写入知识库文档。')
        minutes.archived_document_id = document_id
        meeting.status = 'archived'
        meeting.revision += 1
        meeting.updated_at = datetime.now(timezone.utc)
        await db.flush()
        await notify(db, meeting_id)
        return await _workspace(MeetingsRepository(db), meeting)


async def save_document(meeting_id, user_id, epoch=None, share=None):
    """按自动保存节奏生成正文快照，同一版本重复请求不写入。"""
    async with session.transaction() as db:
        meeting, record = await access(db, meeting_id, user_id, share)
        if record is None or record.kind != 'minutes' or (epoch is not None and record.epoch != epoch):
            raise conflict('文档版本已变化，请保留未同步内容并重新加载。')
        if record.saved_revision < record.revision:
            if not editable(meeting):
                raise conflict('纪要已锁定，不能保存修改。')
            await sync_minutes(db, meeting, record)
            last = await db.scalar(select(MeetingRecordVersion).where(MeetingRecordVersion.meeting_id == meeting_id, MeetingRecordVersion.kind == 'minutes').order_by(MeetingRecordVersion.created_at.desc()).limit(1))
            if last is None or (record.saved_at - last.created_at).total_seconds() >= 60:
                snapshot(db, record, user_id, '自动版本')
            await db.flush()
            await notify(db, meeting_id)
        return output(meeting, record, user_id)
