"""协作合并、版本权限、恢复和生成输入的数据库验证。"""
import asyncio
import base64
from uuid import uuid4
import pytest
from pycrdt import Doc, XmlFragment
from sqlalchemy import delete
from fastapi.testclient import TestClient
from src.core import config
from src.core.exceptions import ApiError
from src.core.security import create_access_token
from src.infrastructure.database import session
from src.main import create_app
from src.modules.users import service as users
from src.modules.users.models import User
from src.modules.meetings import service, records, generation
from src.modules.meetings.models import Meeting, MeetingGenerationJob, MeetingMinutes
from src.modules.meetings.schemas import MeetingCreate, MeetingSave, GenerateMinutes


def append(state, value):
    doc = Doc(); doc.apply_update(base64.b64decode(state))
    before = doc.get_state()
    doc.get('document', type=XmlFragment).children[0].children[1].children[0].children[0].insert(0, value)
    return doc.get_update(before)


async def seed(generated=True):
    owner = await users.create_user(f'record-owner-{uuid4().hex}', 'test', 'product')
    peer = await users.create_user(f'record-peer-{uuid4().hex}', 'test', 'product')
    workspace = await service.create(owner.id, MeetingCreate(title='协作原文测试'))
    body = workspace.model_dump()
    body['meeting']['status'] = 'ended'
    body['segments'] = [{'id': 'raw', 'seq': 0, 'text': '初始转写', 'start_ms': 0}]
    await service.save(owner.id, workspace.meeting.id, MeetingSave(**body, expected_revision=1))
    if generated:
        async with session.transaction() as db:
            meeting = await db.get(Meeting, workspace.meeting.id)
            meeting.generation_status = 'ready'
            db.add(MeetingMinutes(meeting_id=meeting.id, content='# 会议纪要\n\n初始纪要', status=1))
    return owner, peer, workspace.meeting.id


async def cleanup(owner, peer):
    async with session.transaction() as db:
        await db.execute(delete(Meeting).where(Meeting.owner_id == owner.id))
        from src.modules.knowledge.models import KnowledgeBase
        await db.execute(delete(KnowledgeBase).where(KnowledgeBase.owner_id == owner.id))
        await db.execute(delete(User).where(User.id.in_([owner.id, peer.id])))


def test_merge_versions_permissions_and_generation():
    async def case():
        await session.init_db()
        owner, peer, mid = await seed()
        try:
            doc = await records.get_document(mid, owner.id)
            with pytest.raises(ApiError): await records.get_document(mid, peer.id)
            token = (await records.share_document(mid, owner.id))['token']
            assert (await records.resolve_share(token, peer.id))['owner'] is False
            one, two = append(doc['state'], '甲的意见'), append(doc['state'], '乙的意见')
            await asyncio.gather(records.update_document(mid, owner.id, doc['epoch'], one), records.update_document(mid, peer.id, doc['epoch'], two, token))
            merged = await records.get_document(mid, owner.id)
            content = records.minutes_from_state(base64.b64decode(merged['state']))[0]
            assert '甲的意见' in content and '乙的意见' in content and '初始纪要' in content
            original = (await records.list_versions(mid, owner.id))[0]
            await records.checkpoint(mid, owner.id, '团队共识')
            with pytest.raises(ApiError): await records.checkpoint(mid, peer.id, '越权版本')
            with pytest.raises(ApiError): await records.restore(mid, peer.id, original['id'], merged['revision'])
            restored = await records.restore(mid, owner.id, original['id'], merged['revision'])
            assert restored['epoch'] != doc['epoch']
            assert '甲的意见' not in records.minutes_from_state(base64.b64decode(restored['state']))[0]
            assert any(row['label'] == '恢复前自动备份' for row in await records.list_versions(mid, owner.id))
            with pytest.raises(ApiError): await records.update_document(mid, owner.id, doc['epoch'], one)
            await records.update_document(mid, peer.id, restored['epoch'], append(restored['state'], '整理后的内容'), token)
            await records.save_document(mid, peer.id, restored['epoch'], token)
            workspace = await service.get(owner.id, mid)
            assert '整理后的内容' in workspace.minutes.content
            assert workspace.segments[0].text == '初始转写'
            stale = workspace.model_dump()
            stale['minutes']['content'] = '旧页面覆盖'
            with pytest.raises(ApiError):
                await service.save(owner.id, mid, MeetingSave(**stale, expected_revision=workspace.meeting.revision))
            with pytest.raises(ApiError): await records.archive_minutes(mid, peer.id, 1)
            from src.modules.knowledge.repository import KnowledgeRepository
            async with session.transaction() as db:
                base = await KnowledgeRepository(db).create(owner.id, '归档测试', '')
                base_id = base.id
            archived = await records.archive_minutes(mid, owner.id, base_id)
            assert archived.meeting.status == 'archived'
            async with session.read_session() as db:
                document = await KnowledgeRepository(db).get_document(base_id, f'meeting-{mid}')
                assert '整理后的内容' in document.content and document.blocks
            with pytest.raises(ApiError): await records.update_document(mid, peer.id, restored['epoch'], two, token)
        finally:
            await cleanup(owner, peer); await session.close_db()
    asyncio.run(case())


def test_websocket_persists_before_ack(monkeypatch):
    monkeypatch.setattr(config, 'MINUTES_WORKER_ENABLED', False)
    monkeypatch.setattr(config, 'BOOTSTRAP_ADMIN_ENABLED', False)
    async def prepare():
        await session.init_db(); result = await seed(); await session.close_db(); return result
    owner, peer, mid = asyncio.run(prepare())
    try:
        with TestClient(create_app()) as client:
            headers = {'Authorization': f'Bearer {create_access_token(owner.id,owner.role,owner.department)}'}
            assert client.get(f'/api/meetings/{mid}/record').status_code == 401
            token = client.post(f'/api/meetings/{mid}/record/share', headers=headers).json()['data']['token']
            with client.websocket_connect(f'/api/meetings/{mid}/record/events') as ws:
                ws.send_json({'token': create_access_token(peer.id,peer.role,peer.department), 'share_token': token})
                state = ws.receive_json()
                assert state['type'] == 'state'
                ws.send_json({'type':'update','epoch':state['epoch'],'seq':1,'update':base64.b64encode(append(state['state'],'协作输入')).decode()})
                ack = ws.receive_json()
                assert ack['type'] == 'ack' and ack['seq'] == 1
                reread = client.get(f'/api/meetings/{mid}/record', headers=headers).json()['data']
                assert '协作输入' in records.minutes_from_state(base64.b64decode(reread['state']))[0]
                event = ws.receive_json()
                assert event['type'] == 'state' and event['revision'] == ack['revision']
    finally:
        async def remove():
            await session.init_db(); await cleanup(owner, peer); await session.close_db()
        asyncio.run(remove())


def test_original_transcript_has_no_collaboration_and_generation_uses_segments():
    async def case():
        await session.init_db()
        owner, peer, mid = await seed(False)
        try:
            with pytest.raises(ApiError): await records.get_document(mid, owner.id)
            with pytest.raises(ApiError): await records.share_document(mid, owner.id)
            workspace = await service.get(owner.id, mid)
            body = workspace.model_dump()
            body['segments'][0]['text'] = '修正后的转写'
            body['segments'][0]['revision'] += 1
            corrected = await service.save(owner.id, mid, MeetingSave(**body, expected_revision=workspace.meeting.revision))
            accepted = await generation.enqueue(owner.id, mid, GenerateMinutes(expected_revision=corrected.meeting.revision))
            async with session.read_session() as db:
                from src.modules.meetings.models import MeetingSegment
                segment = await db.get(MeetingSegment, (mid, 'raw'))
                assert segment.original_text == '初始转写'
                job = await db.get(MeetingGenerationJob, accepted.task_id)
                assert job.input['segments'][0]['text'] == '修正后的转写'
        finally:
            await cleanup(owner, peer); await session.close_db()
    asyncio.run(case())


def test_legacy_original_share_is_not_reused_for_minutes():
    async def case():
        from src.modules.meetings.record_models import MeetingRecord, MeetingRecordVersion
        from src.modules.meetings.rich_text import state_from_minutes
        await session.init_db()
        owner, peer, mid = await seed()
        try:
            async with session.transaction() as db:
                db.add(MeetingRecord(meeting_id=mid, state=state_from_minutes('旧的原文协作内容'), epoch=str(uuid4()), revision=3, share_token='old-link', kind='original'))
            with pytest.raises(ApiError): await records.resolve_share('old-link', peer.id)
            document = await records.get_document(mid, owner.id)
            assert '初始纪要' in document['content'] and '旧的原文' not in document['content']
            async with session.read_session() as db:
                from sqlalchemy import select
                backups = (await db.scalars(select(MeetingRecordVersion).where(MeetingRecordVersion.meeting_id == mid, MeetingRecordVersion.kind == 'original'))).all()
                assert backups and '旧的原文协作内容' in records.minutes_from_state(backups[0].state)[0]
                assert (await db.get(MeetingRecord,mid)).share_token is None
            assert all(row['label'] != '旧原文协作备份' for row in await records.list_versions(mid,owner.id))
        finally:
            await cleanup(owner,peer); await session.close_db()
    asyncio.run(case())


def test_two_users_receive_each_others_updates_without_http_refresh(monkeypatch):
    monkeypatch.setattr(config, 'MINUTES_WORKER_ENABLED', False)
    monkeypatch.setattr(config, 'BOOTSTRAP_ADMIN_ENABLED', False)
    async def prepare():
        await session.init_db()
        result = await seed()
        await session.close_db()
        return result
    owner, peer, mid = asyncio.run(prepare())
    try:
        with TestClient(create_app()) as client:
            headers = {'Authorization': f'Bearer {create_access_token(owner.id, owner.role, owner.department)}'}
            share = client.post(f'/api/meetings/{mid}/record/share', headers=headers).json()['data']['token']
            path = f'/api/meetings/{mid}/record/events'
            with client.websocket_connect(path) as first, client.websocket_connect(path) as second:
                first.send_json({'token': create_access_token(owner.id, owner.role, owner.department)})
                initial = first.receive_json()
                second.send_json({'token': create_access_token(peer.id, peer.role, peer.department), 'share_token': share})
                assert second.receive_json()['type'] == 'state'
                first.send_json({'type': 'update', 'seq': 1, 'epoch': initial['epoch'], 'update': base64.b64encode(append(initial['state'], '创建者意见')).decode()})
                assert first.receive_json()['type'] == 'ack'
                assert first.receive_json()['type'] == 'state'
                remote = second.receive_json()
                assert remote['type'] == 'state' and '创建者意见' in remote['content']
                second.send_json({'type': 'update', 'seq': 1, 'epoch': remote['epoch'], 'update': base64.b64encode(append(remote['state'], '同事意见')).decode()})
                assert second.receive_json()['type'] == 'ack'
                assert second.receive_json()['type'] == 'state'
                merged = first.receive_json()
                assert '创建者意见' in merged['content'] and '同事意见' in merged['content']
    finally:
        async def remove():
            await session.init_db()
            await cleanup(owner, peer)
            await session.close_db()
        asyncio.run(remove())


def test_live_updates_are_durable_but_body_saves_are_batched_and_idempotent():
    async def case():
        await session.init_db()
        owner, peer, mid = await seed()
        try:
            doc = await records.get_document(mid, owner.id)
            updated = await records.update_document(mid, owner.id, doc['epoch'], append(doc['state'], '连续编辑'))
            assert updated['revision'] > updated['saved_revision']
            assert '连续编辑' in (await records.get_document(mid,owner.id))['content']
            before = await service.get(owner.id,mid)
            assert '连续编辑' not in before.minutes.content
            saved = await records.save_document(mid,owner.id,doc['epoch'])
            assert saved['saved_revision'] == saved['revision']
            after = await service.get(owner.id,mid)
            assert '连续编辑' in after.minutes.content
            await records.save_document(mid,owner.id,doc['epoch'])
            assert (await service.get(owner.id,mid)).meeting.revision == after.meeting.revision
        finally:
            await cleanup(owner,peer); await session.close_db()
    asyncio.run(case())


def test_body_save_failure_can_retry_on_same_websocket(monkeypatch):
    monkeypatch.setattr(config, 'MINUTES_WORKER_ENABLED', False)
    monkeypatch.setattr(config, 'BOOTSTRAP_ADMIN_ENABLED', False)
    async def prepare():
        await session.init_db(); result = await seed(); await session.close_db(); return result
    owner, peer, mid = asyncio.run(prepare())
    original_save = records.save_document
    calls = 0
    async def flaky_save(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1: raise RuntimeError('temporary save failure')
        return await original_save(*args, **kwargs)
    monkeypatch.setattr(records, 'save_document', flaky_save)
    try:
        with TestClient(create_app()) as client:
            with client.websocket_connect(f'/api/meetings/{mid}/record/events') as ws:
                ws.send_json({'token': create_access_token(owner.id, owner.role, owner.department)})
                initial = ws.receive_json()
                ws.send_json({'type': 'save', 'save_seq': 1, 'epoch': initial['epoch']})
                assert ws.receive_json()['type'] == 'save.error'
                ws.send_json({'type': 'save', 'save_seq': 2, 'epoch': initial['epoch']})
                response = ws.receive_json()
                assert response['type'] == 'saved' and response['save_seq'] == 2
    finally:
        async def remove():
            await session.init_db(); await cleanup(owner, peer); await session.close_db()
        asyncio.run(remove())
