"""工具风险判断：普通文档直接操作，敏感写入及高风险命令需要审批。"""
import shlex
from dataclasses import dataclass
from pathlib import Path

SAFE_COMMANDS = {'pwd', 'ls', 'cat', 'head', 'tail', 'wc', 'grep', 'rg', 'stat', 'du', 'df', 'whoami', 'uname', 'echo'}
SENSITIVE_PARTS = {'.git', '.ssh', '.aws', '.kube', 'skills', 'agent.md', 'agents.md', 'credentials', 'id_rsa', 'id_ed25519'}


def sensitive_path(value: str) -> bool:
    """凭证、提示词和技能变更需要人工确认。"""
    if not isinstance(value, str) or not value.strip():
        return True
    return any(part.lower() in SENSITIVE_PARTS or part.lower().startswith('.env')
               for part in Path(value).parts)


def dangerous_command(command: str) -> bool:
    """逐条校验只读命令链；重定向、替换、管道和未知命令必须审批。"""
    if not isinstance(command, str) or not command.strip() or any(char in command for char in '\n\r<>`$(){}\\'):
        return True
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|')
        lexer.whitespace_split = True
        lexer.commenters = ''
        tokens = list(lexer)
    except ValueError:
        return True
    segments, words = [], []
    for token in tokens:
        if token in (';', '&&'):
            if not words:
                return True
            segments.append(words)
            words = []
        elif any(char in token for char in ';&|'):
            return True
        else:
            words.append(token)
    if not words:
        return True
    segments.append(words)
    for words in segments:
        if words[0] not in SAFE_COMMANDS:
            return True
        # rg 的预处理器能够执行外部程序，不属于只读搜索。
        if any(sensitive_path(word) or word.startswith(('--pre', '--hostname-bin')) for word in words[1:]):
            return True
    return False


@dataclass(frozen=True)
class PermissionDecision:
    """审批判断与原因；批准只放行本次参数，不改变沙箱权限。"""
    requires_approval: bool
    reason: str


def evaluate_permission(call: dict) -> PermissionDecision:
    """Permission Manager：只读检查和普通文件操作允许，其余保守审批。"""
    args = call.get('args')
    if not isinstance(args, dict):
        return PermissionDecision(True, '工具参数无法识别')
    if call.get('name') == 'execute':
        required = dangerous_command(args.get('command', ''))
        return PermissionDecision(required, '脚本、写入或未知命令需要确认' if required else '只读命令')
    if call.get('name') in ('write_file', 'edit_file'):
        required = sensitive_path(args.get('file_path', ''))
        return PermissionDecision(required, '敏感文件变更需要确认' if required else '工作目录内普通文件变更')
    return PermissionDecision(True, '未分类工具需要确认')


def needs_approval(request) -> bool:
    """在工具产生副作用前，通过 LangChain HITL 暂停并等待用户决定。"""
    return evaluate_permission(request.tool_call).requires_approval
