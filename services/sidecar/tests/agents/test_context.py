"""工作区提示词在每次运行读取，保留用户修改并隔离不同 Agent。"""
import json
import pytest
from src import config
from src.agents.context import system_prompt
from src.providers.llm.schemas import ModelError


def test_prompt_initializes_once_and_reads_latest_file(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path)
    assert '通用 Agent' in system_prompt('general')
    file = tmp_path / 'general/AGENT.md'
    file.write_text('自定义部门规范：先核对预算。', encoding='utf-8')
    assert system_prompt('general').startswith('自定义部门规范：先核对预算。')
    assert '自定义部门规范' not in system_prompt('product')
    assert file.read_text() == '自定义部门规范：先核对预算。'
    file.write_text('新规范', encoding='utf-8')
    result = system_prompt('general', {'search_knowledge'})
    assert result.startswith('新规范')
    context = json.loads(result.split('<runtime_context>\n')[1].split('\n</runtime_context>')[0])
    assert context['agent_code'] == 'general'
    assert 'search_knowledge' in context['available_tools']


@pytest.mark.parametrize('content', [b'   ', b'\xff', b'a' * (64 * 1024 + 1)])
def test_invalid_prompt_reports_configuration_error(monkeypatch, tmp_path, content):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path)
    folder = tmp_path / 'general'
    folder.mkdir()
    (folder / 'AGENT.md').write_bytes(content)
    with pytest.raises(ModelError) as error:
        system_prompt('general')
    assert error.value.code == 'AGENT_PROMPT_INVALID'
    assert (folder / 'AGENT.md').read_bytes() == content


def test_config_rpc_returns_workspace_prompt_without_runtime_context(monkeypatch, tmp_path):
    import asyncio
    from pydantic import ValidationError
    from src.transport.handlers import agent_config
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path)
    system_prompt('product')
    (tmp_path / 'product/AGENT.md').write_text('本机产品规范', encoding='utf-8')
    result = asyncio.run(agent_config({'agent_code': 'product'}, None))
    assert result == {'agent_code': 'product', 'prompt': '本机产品规范', 'prompt_file': 'AGENT.md'}
    with pytest.raises(ValidationError):
        asyncio.run(agent_config({'agent_code': '../general'}, None))


def test_save_prompt_persists_and_rejects_stale_edits(monkeypatch, tmp_path):
    from src.agents.context import read_prompt, save_prompt
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path)
    original = read_prompt('general')
    product = read_prompt('product')
    assert save_prompt('general', '新提示词', original) == '新提示词'
    assert read_prompt('general') == '新提示词'
    assert system_prompt('general').startswith('新提示词')
    assert read_prompt('product') == product
    with pytest.raises(ModelError) as error:
        save_prompt('general', '过期覆盖', original)
    assert error.value.code == 'AGENT_PROMPT_CONFLICT'
    assert read_prompt('general') == '新提示词'
    for invalid in ('   ', '中' * 65536):
        with pytest.raises(ModelError):
            save_prompt('general', invalid, '新提示词')
    assert read_prompt('general') == '新提示词'


def test_save_failure_keeps_original_and_cleans_temporary_file(monkeypatch, tmp_path):
    from src.agents import context
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path)
    original = context.read_prompt('general')
    def fail(*args):
        raise OSError('fixture')
    monkeypatch.setattr(context.os, 'replace', fail)
    with pytest.raises(ModelError) as error:
        context.save_prompt('general', 'replacement', original)
    assert error.value.code == 'AGENT_PROMPT_SAVE_FAILED'
    assert context.read_prompt('general') == original
    assert not list((tmp_path / 'general').glob('.agent-*.tmp'))
