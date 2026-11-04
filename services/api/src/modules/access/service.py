"""PG 策略是唯一授权来源，每次校验读取快照，跨进程立即使用新策略。"""
from sqlalchemy import select, delete, text
from src.core.exceptions import ApiError
from src.core.responses import ApiCode
from src.infrastructure.database import session
from src.modules.users.models import User
from .models import RolePermission, AccessAudit
from .policy import ROLES, PERMISSIONS, enforcer_for


def forbidden():
    return ApiError(ApiCode.FORBIDDEN, '无权限执行该操作', 403)


async def policy_snapshot(db):
    return tuple((await db.execute(select(RolePermission.role, RolePermission.permission).order_by(
        RolePermission.role, RolePermission.permission))).all())


async def check(db, user, *permissions):
    if user is None or not user.is_active or user.role not in ROLES:
        raise forbidden()
    enforcer = enforcer_for(await policy_snapshot(db))
    if not all(permission in PERMISSIONS and enforcer.enforce(user.role, permission) for permission in permissions):
        raise forbidden()


async def authorize(user, *permissions):
    async with session.read_session() as db:
        await check(db, user, *permissions)


async def authorize_id(user_id, *permissions, db=None):
    """WebSocket/内部回调不用 JWT 中的旧 role，重新读取当前数据库用户。"""
    if db is None:
        async with session.read_session() as current:
            return await authorize_id(user_id, *permissions, db=current)
    user = await db.get(User, user_id, populate_existing=True)
    await check(db, user, *permissions)
    return user


async def my_permissions(user):
    async with session.read_session() as db:
        enforcer = enforcer_for(await policy_snapshot(db))
        return {'role': user.role, 'permissions': [p for p in PERMISSIONS if user.role in ROLES and enforcer.enforce(user.role, p)]}


async def list_roles():
    async with session.read_session() as db:
        policies = await policy_snapshot(db)
        enforcer = enforcer_for(policies)
        return [{'role': role, 'permissions': sorted(p for r, p in policies if r == role),
                 'effective_permissions': [p for p in PERMISSIONS if enforcer.enforce(role, p)]} for role in ROLES]


async def lock_administration(db, actor_id):
    # 串行化管理员变更，避免两个管理员同时相互降权，导致最后一个管理员消失。
    await db.execute(text('SELECT pg_advisory_xact_lock(24702501)'))
    return await authorize_id(actor_id, 'access:manage', db=db)


async def ensure_management_available(db):
    """角色名不代表权限；至少保留一位有效用户拥有管理能力。"""
    manager = await db.scalar(select(User.id).join(RolePermission, RolePermission.role == User.role).where(
        User.status == 0, RolePermission.permission == 'access:manage').limit(1))
    if manager is None:
        raise ApiError(ApiCode.STATE_CONFLICT, '至少需要保留一位拥有用户与权限管理能力的有效用户。', 409)


async def set_role(actor_id, user_id, role):
    if role not in ROLES:
        raise ApiError(ApiCode.PARAM_ERROR, '角色不存在', 422)
    async with session.transaction() as db:
        await lock_administration(db, actor_id)
        target = await db.get(User, user_id, with_for_update=True)
        if target is None:
            raise ApiError(ApiCode.NOT_FOUND, '用户不存在', 404)
        if target.role == role:
            return target.to_public()
        before = target.role
        target.role = role
        db.add(AccessAudit(actor_id=actor_id, action='user.role', target=str(user_id), before={'role': before}, after={'role': role}))
        await db.flush()
        await ensure_management_available(db)
        await db.refresh(target)
        result = target.to_public()
        from src.infrastructure.database.notifications import notify
        await notify(db, 'access_changed', {'user_id': user_id})
    return result


async def set_permissions(actor_id, role, permissions):
    if role not in ROLES:
        raise ApiError(ApiCode.PARAM_ERROR, '角色不存在。', 422)
    values = sorted(set(permissions))
    if any(p not in PERMISSIONS for p in values):
        raise ApiError(ApiCode.PARAM_ERROR, '无效权限。', 422)
    async with session.transaction() as db:
        await lock_administration(db, actor_id)
        before = list((await db.scalars(select(RolePermission.permission).where(RolePermission.role == role))).all())
        await db.execute(delete(RolePermission).where(RolePermission.role == role))
        db.add_all([RolePermission(role=role, permission=p) for p in values])
        await db.flush()
        await ensure_management_available(db)
        db.add(AccessAudit(actor_id=actor_id, action='role.permissions', target=role,
            before={'permissions': sorted(before)}, after={'permissions': values}))
        from src.infrastructure.database.notifications import notify
        await notify(db, 'access_changed', {'role': role})
    return {'role': role, 'permissions': values}
