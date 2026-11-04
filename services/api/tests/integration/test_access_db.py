"""真实 PG + JWT + HTTP 验证角色权限，不覆盖认证依赖。"""
import asyncio
from uuid import uuid4
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from src.core.exceptions import ApiError
from src.core.security import create_access_token
from src.infrastructure.database import session
from src.main import create_app
from src.modules.users import service as users
from src.modules.users.models import User
from src.modules.access import service as access
from src.modules.access.models import AccessAudit
from src.modules.access.policy import MEMBER_PERMISSIONS


async def seed(role):
    return await users.create_user('rbac-' + uuid4().hex, 'fixture-only', 'product', role=role)


def headers(user):
    # 特意使用旧的 admin claim，权限必须取数据库当前角色。
    return {'Authorization': 'Bearer ' + create_access_token(user.id, 'admin', 'platform')}


def test_http_roles_revocation_and_resource_ownership():
    async def case():
        await session.init_db()
        try:
            admin, member = await seed('admin'), await seed('member')
            async with AsyncClient(transport=ASGITransport(app=create_app()), base_url='http://test') as client:
                ordinary = headers(member)
                me = await client.get('/api/access/me', headers=ordinary)
                assert me.status_code == 200
                assert 'access:manage' not in me.json()['data']['permissions']
                assert (await client.put(f'/api/access/users/{member.id}/role', headers=ordinary, json={'role': 'admin'})).status_code == 403
                base = await client.post('/api/knowledge-bases', headers=ordinary, json={'name': 'Owned by member'})
                assert base.status_code == 200
                base_id = base.json()['data']['id']
                # 平台管理员也不绕过业务资源归属。
                assert (await client.put(f'/api/knowledge-bases/{base_id}', headers=headers(admin), json={'name': 'steal'})).status_code == 404
                changed = await client.put(f'/api/access/users/{member.id}/role', headers=headers(admin), json={'role': 'viewer'})
                assert changed.status_code == 200
                assert changed.json()['data']['role'] == 'viewer'
                # 同一个旧 JWT 在降权后立即禁止写入，但仍可读本人知识库。
                assert (await client.post('/api/knowledge-bases', headers=ordinary, json={'name': 'denied'})).status_code == 403
                assert (await client.get('/api/knowledge-bases', headers=ordinary)).status_code == 200
                assert (await client.get('/api/access/roles', headers=ordinary)).status_code == 403
                assert (await client.put('/api/access/roles/viewer/permissions', headers=headers(admin), json={'permissions': ['invalid:permission']})).status_code == 422
            async with session.read_session() as db:
                audits = (await db.scalars(select(AccessAudit).where(AccessAudit.target == str(member.id)))).all()
                assert len(audits) == 1
                assert audits[0].before == {'role': 'member'}
                assert audits[0].after == {'role': 'viewer'}
        finally:
            await session.close_db()
    asyncio.run(case())


def test_policy_change_is_visible_to_a_previously_loaded_enforcer():
    async def case():
        await session.init_db()
        try:
            admin, member, manager = await seed('admin'), await seed('member'), await seed('manager')
            await access.authorize(member, 'knowledge:write')
            await access.authorize(manager, 'knowledge:write')
            try:
                await access.set_permissions(admin.id, 'member', [p for p in MEMBER_PERMISSIONS if p != 'knowledge:write'])
                with pytest.raises(ApiError) as error:
                    await access.authorize(member, 'knowledge:write')
                assert error.value.status_code == 403
                await access.authorize(manager, 'knowledge:write')
                await access.authorize(admin, 'knowledge:write')
            finally:
                await access.set_permissions(admin.id, 'member', MEMBER_PERMISSIONS)
            await access.authorize(member, 'knowledge:write')
        finally:
            await session.close_db()
    asyncio.run(case())


def test_last_admin_is_protected():
    async def case():
        await session.init_db()
        try:
            admin = await seed('admin')
            async with session.transaction() as db:
                other_ids = list((await db.scalars(select(User.id).where(User.role == 'admin', User.id != admin.id, User.status == 0))).all())
                if other_ids:
                    await db.execute(update(User).where(User.id.in_(other_ids)).values(status=1))
            try:
                with pytest.raises(ApiError) as error:
                    await access.set_role(admin.id, admin.id, 'member')
                assert error.value.status_code == 409
            finally:
                if other_ids:
                    async with session.transaction() as db:
                        await db.execute(update(User).where(User.id.in_(other_ids)).values(status=0))
        finally:
            await session.close_db()
    asyncio.run(case())


def test_concurrent_admin_demotion_revalidates_actor():
    async def case():
        await session.init_db()
        try:
            one, two = await seed('admin'), await seed('admin')
            results = await asyncio.gather(access.set_role(one.id, two.id, 'member'),
                                           access.set_role(two.id, one.id, 'member'), return_exceptions=True)
            assert sum(isinstance(value, ApiError) for value in results) == 1
            async with session.read_session() as db:
                roles = list((await db.scalars(select(User.role).where(User.id.in_([one.id, two.id])))).all())
                assert sorted(roles) == ['admin', 'member']
        finally:
            await session.close_db()
    asyncio.run(case())


def test_viewer_can_read_shared_minutes_but_cannot_write_crdt():
    async def case():
        import base64
        from pycrdt import Doc
        from src.modules.meetings import service as meetings, records
        from src.modules.meetings.models import Meeting, MeetingMinutes
        from src.modules.meetings.schemas import MeetingCreate
        await session.init_db()
        try:
            owner, viewer = await seed('member'), await seed('viewer')
            workspace = await meetings.create(owner.id, MeetingCreate(title='Readonly shared minutes'))
            mid = workspace.meeting.id
            async with session.transaction() as db:
                meeting = await db.get(Meeting, mid)
                meeting.status, meeting.generation_status = 'ended', 'ready'
                db.add(MeetingMinutes(meeting_id=mid, content='# Original minutes', status=1))
            token = (await records.share_document(mid, owner.id))['token']
            current = await records.resolve_share(token, viewer.id)
            assert current['editable'] is False
            assert current['locked'] is False
            doc = Doc()
            doc.apply_update(base64.b64decode(current['state']))
            with pytest.raises(ApiError) as error:
                await records.update_document(mid, viewer.id, current['epoch'], doc.get_update(), token)
            assert error.value.status_code == 403
            assert (await records.resolve_share(token, viewer.id))['revision'] == current['revision']
        finally:
            await session.close_db()
    asyncio.run(case())


def test_rag_capability_rechecks_current_policy():
    async def case():
        from src.modules.knowledge import rag_access
        from src.modules.access.policy import VIEWER_PERMISSIONS
        await session.init_db()
        try:
            admin, viewer = await seed('admin'), await seed('viewer')
            token = rag_access.issue_capability(viewer.id, [1])
            assert (await rag_access.authorized_scope(token))[0] == viewer.id
            try:
                await access.set_permissions(admin.id, 'viewer', ['meeting:read'])
                with pytest.raises(ApiError) as error:
                    await rag_access.authorized_scope(token)
                assert error.value.status_code == 403
            finally:
                await access.set_permissions(admin.id, 'viewer', VIEWER_PERMISSIONS)
        finally:
            await session.close_db()
    asyncio.run(case())


def test_all_roles_can_be_configured_and_management_can_be_delegated():
    async def case():
        from src.modules.access.policy import PERMISSIONS, VIEWER_PERMISSIONS
        await session.init_db()
        try:
            admin, manager, viewer = await seed('admin'), await seed('manager'), await seed('viewer')
            original = {item['role']: item['permissions'] for item in await access.list_roles()}
            try:
                # 管理员自身的业务权限也可以撤销，不再被固定策略放行。
                await access.set_permissions(admin.id, 'admin', [p for p in PERMISSIONS if p != 'knowledge:delete'])
                with pytest.raises(ApiError):
                    await access.authorize(admin, 'knowledge:delete')
                await access.authorize(manager, 'knowledge:delete')
                await access.set_permissions(admin.id, 'manager', ['knowledge:read'])
                with pytest.raises(ApiError):
                    await access.authorize(manager, 'knowledge:write')
                member = await seed('member')
                await access.authorize(member, 'knowledge:write')
                # 可以显式授权其他角色管理能力，授权后才能修改策略。
                await access.set_permissions(admin.id, 'viewer', [*VIEWER_PERMISSIONS, 'access:manage'])
                await access.authorize(viewer, 'access:manage')
                await access.set_permissions(admin.id, 'admin', [])
                with pytest.raises(ApiError):
                    await access.authorize(admin, 'access:manage')
                await access.set_permissions(viewer.id, 'admin', original['admin'])
            finally:
                # 如果断言中断在管理员降权之后，由仍有管理权限的角色恢复测试策略。
                candidates = [admin, viewer]
                for candidate in candidates:
                    try:
                        await access.authorize(candidate, 'access:manage')
                    except ApiError:
                        continue
                    await access.set_permissions(candidate.id, 'admin', original['admin'])
                    break
                for role in ('manager', 'member', 'viewer'):
                    await access.set_permissions(admin.id, role, original[role])
        finally:
            await session.close_db()
    asyncio.run(case())


def test_policy_change_cannot_remove_last_management_capability():
    async def case():
        from src.modules.access.policy import PERMISSIONS
        await session.init_db()
        try:
            admin = await seed('admin')
            async with session.transaction() as db:
                other_ids = list((await db.scalars(select(User.id).where(User.role == 'admin', User.id != admin.id, User.status == 0))).all())
                if other_ids:
                    await db.execute(update(User).where(User.id.in_(other_ids)).values(status=1))
            try:
                with pytest.raises(ApiError) as error:
                    await access.set_permissions(admin.id, 'admin', [])
                assert error.value.status_code == 409
                # 拒绝时整个策略替换回滚，原管理权限继续有效。
                await access.authorize(admin, 'access:manage')
                assert next(r for r in await access.list_roles() if r['role'] == 'admin')['permissions'] == sorted(PERMISSIONS)
            finally:
                if other_ids:
                    async with session.transaction() as db:
                        await db.execute(update(User).where(User.id.in_(other_ids)).values(status=0))
        finally:
            await session.close_db()
    asyncio.run(case())
