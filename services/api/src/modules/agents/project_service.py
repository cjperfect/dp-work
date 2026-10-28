"""项目管理仅存元信息，不对云端路径进行文件读写。"""
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from src.core.exceptions import ApiError
from src.core.responses import ApiCode
from src.infrastructure.database import session
from src.modules.devices.models import Device
from .project_models import AgentProject
from .conversation_models import Conversation


def serialize(row):
    return {key: getattr(row, key) for key in ('id','name','path','device_id','created_at','updated_at')}


async def owned(db, owner, project_id, lock=False):
    """只读取当前用户的项目。"""
    query = select(AgentProject).where(AgentProject.id == project_id, AgentProject.owner_id == owner)
    row = await db.scalar(query.with_for_update() if lock else query)
    if not row: raise ApiError(ApiCode.NOT_FOUND, '项目不存在。', 404)
    return row


async def list_projects(owner):
    async with session.read_session() as db:
        return [serialize(row) for row in await db.scalars(select(AgentProject).where(AgentProject.owner_id == owner).order_by(AgentProject.updated_at.desc()))]


async def create(owner, body):
    """登记已登录用户设备提供的目录元信息，实际授权由 Sidecar 校验。"""
    async with session.transaction() as db:
        device = await db.scalar(select(Device).where(Device.id == body.device_id, Device.owner_id == owner, Device.lease_until > func.now()))
        if not device: raise ApiError(ApiCode.STATE_CONFLICT, '项目设备未连接，请在桌面端重新选择文件夹。', 409)
        await db.execute(insert(AgentProject).values(id=body.id, owner_id=owner, device_id=body.device_id,
            name=body.name, path=body.path).on_conflict_do_nothing(index_elements=[AgentProject.id]))
        row = await db.get(AgentProject, body.id)
        if row.owner_id != owner or row.device_id != body.device_id or row.path != body.path:
            raise ApiError(ApiCode.STATE_CONFLICT, '项目目录不匹配。', 409)
        return serialize(row)


async def rename(owner, key, name):
    async with session.transaction() as db:
        row = await owned(db, owner, key, True)
        if not name.strip(): raise ApiError(ApiCode.PARAM_ERROR, '请输入项目名称。', 400)
        row.name, row.updated_at = name.strip(), func.now()
        await db.flush(); await db.refresh(row)
        return serialize(row)


async def remove(owner, key):
    """移除项目关联，保留历史会话和用户本地文件。"""
    async with session.transaction() as db:
        row = await owned(db, owner, key, True)
        # 与会话修改统一先锁项目再锁会话，避免删除与关联互相覆盖。
        threads = list(await db.scalars(select(Conversation).where(Conversation.project_id == key).with_for_update()))
        for thread in threads:
            if thread.run_token and thread.run_until is not None:
                from datetime import datetime, timezone
                if thread.run_until > datetime.now(timezone.utc):
                    raise ApiError(ApiCode.STATE_CONFLICT, '项目中仍有运行或待审批会话，请先结束后再移除。', 409)
        for thread in threads:
            thread.project_id = None
            thread.draft_revision += 1
        await db.delete(row)


async def set_thread_project(owner, key, body):
    """为当前会话选择工作目录，执行中或待审批时禁止切换。"""
    from .conversation_repository import ConversationRepository
    from .conversation_service import check_revision, detail
    async with session.transaction() as db:
        if body.project_id: await owned(db, owner, body.project_id, True)
        row = await ConversationRepository(db).get(owner, key, lock=True)
        if not row: raise ApiError(ApiCode.NOT_FOUND, '会话不存在。', 404)
        check_revision(row, body.expected_revision)
        row.project_id = body.project_id
        row.draft_revision += 1
        row.updated_at = func.now()
        await db.flush()
        await db.refresh(row)
        return await detail(db, row)
