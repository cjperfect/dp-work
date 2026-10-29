"""图片引用、本机文件和模型输入边界。"""
import asyncio
import base64
import pytest
from src.sessions import images
from src.sessions.storage import SessionStorage, SessionError
from src.agents import agent
from src.providers.llm.schemas import ModelSettings
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

PNG = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()

def test_local_images_are_deduplicated_isolated_and_validated(monkeypatch, tmp_path):
    monkeypatch.setattr(images, 'storage', SessionStorage(tmp_path))
    ref = images.save(1, {'data_url': PNG, 'content_type':'image/png', 'name':'截图.png'})
    assert images.save(1, {'data_url':PNG, 'content_type':'image/png'})['id'] == ref['id']
    assert images.read(1, ref['id'], 'image/png') == PNG
    assert images.model_images(1, [ref]) == [PNG]
    assert 'data_url' not in ref
    with pytest.raises(SessionError): images.read(2, ref['id'], 'image/png')
    with pytest.raises(SessionError): images.read(1, '../secret', 'image/png')
    with pytest.raises(SessionError): images.save(1, {'data_url':'data:image/png;base64,YWJj', 'content_type':'image/png'})
    with pytest.raises(SessionError): images.model_images(1, [ref] * 4)
    assert (images.image_path(1, ref['id']).stat().st_mode & 0o777) == 0o600


def test_image_is_forwarded_as_vision_content_to_model(monkeypatch, tmp_path):
    from src import config
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path/'workspace')
    seen = []
    class Model(FakeMessagesListChatModel):
        def bind_tools(self, *args, **kwargs): return self
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            seen.extend(messages)
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
    monkeypatch.setattr(agent, 'create_model', lambda *_: Model(responses=[AIMessage('已查看图片')]))
    async def case():
        body = agent.AgentRequest(thread_id='image-test', messages=[{'role':'user','content':'图片有什么？','images':[PNG]}])
        events = [event async for event in agent.run_agent(body, ModelSettings(timeout=10))]
        assert events[-1]['type'] == 'done', events
        assert seen[-1].content[1] == {'type':'image_url','image_url':{'url':PNG}}
    asyncio.run(case())
