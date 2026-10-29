"""按参数区分普通工具操作和风险操作。"""
import pytest
from src.harness.tool_policy import dangerous_command, sensitive_path, evaluate_permission


@pytest.mark.parametrize('command', ['pwd', 'ls -la', 'rg -n TODO src', 'cat notes.md', 'echo hello',
    'pwd && ls -la', 'wc -c /c.txt && wc -l /c.txt && head -3 /c.txt',
    "wc -c c.txt; wc -l c.txt; head -3 c.txt; echo '---'; tail -2 c.txt"])
def test_simple_inspection_needs_no_approval(command):
    assert not dangerous_command(command)


@pytest.mark.parametrize('command', [
    'rm -rf docs', 'git reset --hard', 'sudo touch /etc/test',
    'printf data > file.txt', 'ls; rm notes.md', 'echo $(rm notes.md)',
    'cat `whoami`', 'pwd\nrm notes.md', 'bash script.sh',
    'python -c "print(1)"', 'rg --pre=script.py x', 'cat .env', 'date --set=tomorrow',
    'pwd && rm file.txt', 'pwd; printf text > a.txt', 'pwd && rg --pre=script.py x',
    'pwd && cat .env', 'pwd | bash', 'pwd & ls', 'pwd || rm a.txt', 'pwd &&',
])
def test_risky_or_unclassified_commands_require_approval(command):
    assert dangerous_command(command)


@pytest.mark.parametrize('path', ['.env', '/.git/config', '/AGENT.md', '/skills/demo/SKILL.md', '/.ssh/id_rsa'])
def test_sensitive_file_changes_require_approval(path):
    assert sensitive_path(path)


@pytest.mark.parametrize('command', ['python script.py', 'python -c "exec(open(\'script.py\').read())"', 'bash ./safe-looking.sh'])
def test_scripts_always_require_approval_even_when_named_safe(command):
    decision = evaluate_permission({'name': 'execute', 'args': {'command': command}})
    assert decision.requires_approval and decision.reason


def test_permission_manager_handles_invalid_and_ordinary_operations():
    assert evaluate_permission({'name': 'execute', 'args': {'command': None}}).requires_approval
    assert evaluate_permission({'name': 'execute', 'args': []}).requires_approval
    assert evaluate_permission({'name': 'unknown', 'args': {}}).requires_approval
    assert not evaluate_permission({'name': 'write_file', 'args': {'file_path': 'notes.md'}}).requires_approval

