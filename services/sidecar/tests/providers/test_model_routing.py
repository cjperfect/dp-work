"""路由边界：按任务分档、显式选模、完整个人配置与缺省兼容。"""
import pytest
from src import config
from src.providers.llm.routing import route_request
from src.providers.llm.schemas import ModelError, ModelSettings


@pytest.fixture(autouse=True)
def models(monkeypatch):
    for name, value in {
        'ARK_MODEL': 'original', 'ARK_MODEL_LITE': 'cheap',
        'ARK_MODEL_DEFAULT': 'standard', 'ARK_MODEL_STRONG': 'capable',
        'ARK_API_KEY': 'fixture-secret', 'ARK_BASE_URL': 'https://example.com/v1',
    }.items():
        monkeypatch.setattr(config, name, value)


@pytest.mark.parametrize(('task', 'expected'), [
    ('title', 'cheap'), ('memory_extract', 'cheap'),
    ('minutes', 'standard'), ('memory_consolidate', 'standard'),
    ('agent', 'capable'), ('unknown', 'standard'),
])
def test_task_route_preserves_connection(task, expected):
    settings = route_request(task)
    assert settings.model == expected
    assert settings.api_key == 'fixture-secret'
    assert settings.base_url == 'https://example.com/v1'


def test_missing_tiers_preserve_existing_model(monkeypatch):
    for name in ('ARK_MODEL_LITE', 'ARK_MODEL_DEFAULT', 'ARK_MODEL_STRONG'):
        monkeypatch.setattr(config, name, '')
    for task in ('title', 'agent', 'minutes'):
        assert route_request(task).model == 'original'


def test_explicit_model_overrides_tier_but_cannot_inject_arbitrary_id():
    assert route_request('agent', explicit_model='cheap').model == 'cheap'
    assert route_request('title', explicit_model='original').model == 'original'
    with pytest.raises(ModelError, match='所选模型未配置'):
        route_request('agent', explicit_model='unconfigured')


def test_personal_provider_is_not_replaced_by_platform_model():
    personal = ModelSettings(model='personal-model', api_key='personal-key', base_url='https://personal.example/v1')
    assert route_request('title', settings=personal) is personal
    assert route_request('agent', settings=personal, explicit_model='personal-model') is personal
    with pytest.raises(ModelError):
        route_request('agent', settings=personal, explicit_model='cheap')


def test_logs_never_include_credentials(caplog):
    with caplog.at_level('INFO'):
        route_request('title')
    assert 'cheap' in caplog.text
    assert 'fixture-secret' not in caplog.text
