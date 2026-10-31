"""百度 OCR 协议、鉴权缓存、错误脱敏及体积限制。"""
from urllib.parse import parse_qs

import httpx
import pytest

from src import config
from src.providers.ocr.baidu import BaiduOCR, MAX_FORM_BYTES, image_form


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setattr(config, 'BAIDU_OCR_API_KEY', 'fixture-key')
    monkeypatch.setattr(config, 'BAIDU_OCR_SECRET_KEY', 'fixture-secret')


def test_token_reused_and_image_is_form_encoded():
    requests = []
    def handler(request):
        requests.append(request)
        if request.url.path.endswith('/token'):
            data = parse_qs(request.content.decode())
            assert data['client_secret'] == ['fixture-secret']
            assert 'fixture-secret' not in str(request.url)
            return httpx.Response(200, json={'access_token': 'fixture-token', 'expires_in': 3600})
        assert request.url.params['access_token'] == 'fixture-token'
        assert request.url.path.endswith('/accurate_basic')
        assert parse_qs(request.content.decode())['image'] == ['aW1hZ2U=']
        return httpx.Response(200, json={'words_result': [{'words': '容量'}, {'words': '5200mAh'}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        ocr = BaiduOCR(client)
        assert ocr.recognize(b'image') == '容量\n5200mAh'
        assert ocr.recognize(b'image') == '容量\n5200mAh'
    assert len(requests) == 3


def test_expired_token_refreshed_only_once():
    auth, calls = [], []
    def handler(request):
        if request.url.path.endswith('/token'):
            auth.append(request)
            return httpx.Response(200, json={'access_token': f'token-{len(auth)}', 'expires_in': 3600})
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={'error_code': 110})
        return httpx.Response(200, json={'words_result': [{'words': '成功'}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert BaiduOCR(client).recognize(b'image') == '成功'
    assert len(auth) == len(calls) == 2


@pytest.mark.parametrize('payload,message', [
    ({'error_code': 18, 'error_msg': 'fixture-secret'}, '频繁'),
    ({'error_code': 6}, '权限'),
    ({'error_code': 17}, '额度'),
    ({'error_code': 111}, '过期'),
    ({'words_result': 'bad'}, '格式'),
    ({'words_result': [{}]}, '格式'),
    ([], '格式'),
])
def test_errors_are_actionable_and_hide_remote_payload(payload, message):
    def handler(request):
        if request.url.path.endswith('/token'):
            return httpx.Response(200, json={'access_token': 'fixture-token', 'expires_in': 3600})
        return httpx.Response(200, json=payload)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match=message) as error:
            BaiduOCR(client).recognize(b'image')
    assert 'fixture-secret' not in str(error.value)
    assert 'fixture-token' not in str(error.value)


def test_http_failure_does_not_expose_credentials():
    def handler(request):
        raise httpx.ConnectError('fixture-secret in request', request=request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match='连接失败') as error:
            BaiduOCR(client).recognize(b'image')
    assert error.value.__suppress_context__
    assert 'fixture-secret' not in str(error.value)


def test_encoded_size_limit_before_network():
    def forbidden(request):
        pytest.fail('超大图片不能发起网络请求')
    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        with pytest.raises(ValueError, match='图像过大'):
            BaiduOCR(client).recognize(b'x' * MAX_FORM_BYTES)
    assert b'image=' in image_form(b'image')
