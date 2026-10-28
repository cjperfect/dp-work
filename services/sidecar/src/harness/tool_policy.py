"""工具风险判断：普通文档直接操作，敏感写入及高风险命令需要审批。"""
import shlex
from pathlib import Path

SAFE_COMMANDS = {'pwd', 'ls', 'cat', 'head', 'tail', 'wc', 'grep', 'rg', 'stat', 'du', 'df', 'whoami', 'uname', 'echo'}
SENSITIVE_PARTS = {'.git', '.ssh', '.aws', '.kube', 'skills', 'agent.md', 'agents.md', 'credentials', 'id_rsa', 'id_ed25519'}


def sensitive_path(value: str) -> bool:
    """凭证、提示词和技能变更需要人工确认。"""
    return any(part.lower() in SENSITIVE_PARTS or part.lower().startswith('.env')
               for part in Path(value).parts)


def dangerous_command(command: str) -> bool:
    """仅自动执行可静态判断的简单查看命令，复杂 shell 语法必须审批。"""
    if not command.strip() or any(char in command for char in '\n\r;&|<>`$(){}\\'):
        return True
    try:
        words = shlex.split(command)
    except ValueError:
        return True
    if not words or words[0] not in SAFE_COMMANDS:
        return True
    # rg 的预处理器能够执行外部程序，不属于只读搜索。
    return any(sensitive_path(word) or word.startswith(('--pre', '--hostname-bin')) for word in words[1:])


def needs_approval(request) -> bool:
    """由 LangChain HITL 的 when 谓词按实际工具参数决定是否暂停。"""
    call = request.tool_call
    args = call.get('args', {})
    if call['name'] == 'execute':
        return dangerous_command(args.get('command', ''))
    return sensitive_path(args.get('file_path', ''))
