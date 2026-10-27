"""skills.sh 安装、Agent 隔离与 Deep Agents 渐进加载回归。"""
import asyncio
import io
from pathlib import Path
import zipfile

import httpx
import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage

from src import config
from src.agents.agent import build_agent
from src.skills import service

SKILL = b'---\nname: test-skill\ndescription: A fixture for business writing\n---\n\nONLY_AFTER_READ_SECRET_INSTRUCTION\nRead scripts/check.py when needed.\n'


def archive(extra=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as bundle:
        bundle.writestr('repo-HEAD/skills/test-skill/SKILL.md', SKILL)
        bundle.writestr('repo-HEAD/skills/test-skill/scripts/check.py', "raise RuntimeError('must-not-execute-on-install')")
        bundle.writestr('repo-HEAD/other-private.txt', 'not part of this skill')
        if extra:
            bundle.writestr(*extra)
    return output.getvalue()


@pytest.fixture(autouse=True)
def isolated_skills(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path / 'workspace')
    monkeypatch.setattr(config, 'TEMP_DIR', tmp_path / 'temp')
    service.LOCKS.clear()


def test_source_formats_reject_arbitrary_urls():
    assert service.parse_source('https://skills.sh/acme/repo/test-skill') == ('acme/repo', 'test-skill')
    assert service.parse_source('acme/repo@test-skill') == ('acme/repo', 'test-skill')
    for source in ['https://evil.example/a/b/c', 'https://skills.sh:bad/a/b/c', 'acme/repo@../escape', 'acme/repo', 'https://user:pass@skills.sh/a/b/c']:
        with pytest.raises(service.SkillError):
            service.parse_source(source)


def test_install_persists_resources_and_uninstalls_one_agent():
    async def case():
        requests = []
        def handler(request):
            requests.append(request)
            assert str(request.url) == 'https://codeload.github.com/acme/repo/zip/HEAD'
            return httpx.Response(200, content=archive())
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            first = await service.install('general', 'acme/repo@test-skill', client)
            assert await service.install('general', 'acme/repo@test-skill', client) == first
            assert len(requests) == 1
            await service.install('product', 'acme/repo@test-skill', client)
        assert len(service.installed('general')) == len(service.installed('product')) == 1
        root = config.WORKSPACE_DIR / 'general/skills/test-skill'
        assert (root / 'scripts/check.py').is_file()
        assert not (root / 'other-private.txt').exists()
        await service.uninstall('general', first['id'])
        assert not service.installed('general')
        assert service.installed('product')[0]['id'] == first['id']
        assert not list(config.TEMP_DIR.iterdir())
    asyncio.run(case())


def test_search_uses_official_directory():
    async def case():
        def handler(request):
            assert request.url.host == 'skills.sh' and request.url.params['q'] == 'business'
            return httpx.Response(200, json={'skills': [
                {'source': 'acme/repo', 'skillId': 'test-skill', 'installs': 10},
                {'source': '../../bad', 'skillId': 'test-skill'}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            rows = await service.search('business', client)
        assert len(rows) == 1 and rows[0]['id'] == 'acme/repo@test-skill'
    asyncio.run(case())


def test_zip_traversal_does_not_commit():
    async def case():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=archive(('repo-HEAD/skills/test-skill/../../escape.txt', 'bad'))))) as client:
            with pytest.raises(service.SkillError):
                await service.install('general', 'acme/repo@test-skill', client)
        assert not service.installed('general')
        assert not list(config.TEMP_DIR.iterdir())
    asyncio.run(case())


def test_deepagent_loads_only_current_agent_and_reads_skill_on_demand():
    async def case():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=archive()))) as client:
            await service.install('product', 'acme/repo@test-skill', client)
        class Model(FakeMessagesListChatModel):
            def bind_tools(self, *args, **kwargs): return self
            def _generate(self, messages, *args, **kwargs):
                if self.i == 0:
                    assert 'test-skill' in str(messages[0].content)
                    assert 'ONLY_AFTER_READ_SECRET_INSTRUCTION' not in str(messages[0].content)
                else:
                    assert any('ONLY_AFTER_READ_SECRET_INSTRUCTION' in str(message.content) for message in messages[1:])
                return super()._generate(messages, *args, **kwargs)
        model = Model(responses=[
            AIMessage('', tool_calls=[{'name': 'read_file', 'args': {'file_path': '/skills/test-skill/SKILL.md'}, 'id': 'skill', 'type': 'tool_call'}]),
            AIMessage('Skill loaded'),
        ])
        result = await build_agent(model, 'product').ainvoke({'messages': [HumanMessage('Use the skill')]})
        assert result['messages'][-1].content == 'Skill loaded'
        class EmptyModel(FakeMessagesListChatModel):
            def bind_tools(self, *args, **kwargs): return self
            def _generate(self, messages, *args, **kwargs):
                assert 'test-skill' not in str(messages[0].content)
                return super()._generate(messages, *args, **kwargs)
        other = await build_agent(EmptyModel(responses=[AIMessage('No skills')]), 'general').ainvoke({'messages': [HumanMessage('hi')]})
        assert other['messages'][-1].content == 'No skills'
        await service.uninstall('product', 'acme/repo@test-skill')
        await build_agent(EmptyModel(responses=[AIMessage('Removed')]), 'product').ainvoke({'messages': [HumanMessage('hi')]})
    asyncio.run(case())


def test_archive_symlink_and_different_source_are_rejected():
    async def case():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=archive()))) as client:
            await service.install('general', 'acme/repo@test-skill', client)
            with pytest.raises(service.SkillError) as error:
                await service.install('general', 'other/repo@test-skill', client)
            assert error.value.status == 409
        link = zipfile.ZipInfo('repo-HEAD/skills/test-skill/link')
        link.create_system = 3
        link.external_attr = 0o120777 << 16
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=archive((link, '../../private'))))) as client:
            with pytest.raises(service.SkillError):
                await service.install('product', 'acme/repo@test-skill', client)
        assert not service.installed('product')
        assert service.installed('general')[0]['source'] == 'acme/repo'
    asyncio.run(case())


@pytest.mark.parametrize('marker', ['[]', 'null', '{"source": []}', '{"source": "../../invalid"}', '{broken'])
def test_corrupt_marker_does_not_hide_other_skills(marker, caplog):
    root = service.skill_directory('general')
    for name in ('broken', 'healthy'):
        folder = root / name
        folder.mkdir()
        (folder / 'SKILL.md').write_bytes(SKILL.replace(b'test-skill', name.encode()))
    (root / 'broken/.dp-work-skill.json').write_text(marker)
    rows = service.installed('general')
    assert [row['name'] for row in rows] == ['healthy']
    assert '跳过异常技能 broken' in caplog.text


def test_file_work_does_not_block_loop_and_cancellation_keeps_lock(monkeypatch):
    import threading
    started, release = threading.Event(), threading.Event()
    extract = service.extract_skill
    def slow_extract(*args):
        started.set()
        if not release.wait(3):
            raise TimeoutError('test did not release worker')
        return extract(*args)
    monkeypatch.setattr(service, 'extract_skill', slow_extract)
    async def case():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=archive()))) as client:
            task = asyncio.create_task(service.install('general', 'acme/repo@test-skill', client))
            try:
                # The event loop must continue while extraction waits in another thread.
                assert await asyncio.to_thread(started.wait, 1)
                await asyncio.sleep(0)
                assert not task.done()
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
                assert service.LOCKS['general'].locked()
                uninstall = asyncio.create_task(service.uninstall('general', 'acme/repo@test-skill'))
                await asyncio.sleep(0)
                assert not uninstall.done()
            finally:
                release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert await uninstall == {'removed': True}
            assert not service.installed('general')
            assert not list(config.TEMP_DIR.iterdir())
    asyncio.run(case())
