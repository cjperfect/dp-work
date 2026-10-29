"""共享默认提示词，不读取或修改用户工作区。"""
from importlib.resources import files


def read_template(code: str) -> str:
    """读取指定 Agent 的内置默认模板。"""
    if code not in ('general', 'product', 'ui'):
        raise ValueError('不支持的 Agent 模板。')
    return files(__package__).joinpath(code, 'AGENT.md').read_text(encoding='utf-8')
