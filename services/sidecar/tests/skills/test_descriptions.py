"""技能卡片简介取自真实元信息，重复请求使用缓存。"""
import asyncio
import httpx
from src import config
from src.skills.descriptions import descriptions


def test_public_description_is_parsed_and_cached(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    async def case():
        calls = []
        def handler(request):
            calls.append(request)
            assert request.url.host == 'www.skills.sh'
            # Metadata crosses a network chunk boundary; Unicode must remain intact.
            text = ' ' * 8180 + '<meta name="description" content="浏览器自动化：打开网页、填写表单 &amp; 提取数据。">'
            return httpx.Response(200, text=text)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            first = await descriptions(['acme/repo@browser'], client)
            second = await descriptions(['acme/repo@browser'], client)
        assert first == second == {'acme/repo@browser': '浏览器自动化：打开网页、填写表单 & 提取数据。'}
        assert len(calls) == 1
    asyncio.run(case())


def test_failed_item_does_not_hide_other_descriptions(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    async def case():
        def handler(request):
            if request.url.path.endswith('/good'):
                return httpx.Response(200, text='<meta name="description" content="Review documents">')
            return httpx.Response(503)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            rows = await descriptions(['acme/repo@good', 'acme/repo@unavailable', 'invalid'], client)
        assert rows['acme/repo@good'] == 'Review documents'
        assert rows['acme/repo@unavailable'] == rows['invalid'] == ''
    asyncio.run(case())
