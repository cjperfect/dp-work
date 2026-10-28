"""按参数区分普通工具操作和风险操作。"""
import pytest
from src.harness.tool_policy import dangerous_command, sensitive_path


@pytest.mark.parametrize('command', ['pwd', 'ls -la', 'rg -n TODO src', 'cat notes.md', 'echo hello'])
def test_simple_inspection_needs_no_approval(command):
    assert not dangerous_command(command)


@pytest.mark.parametrize('command', [
    'rm -rf docs', 'git reset --hard', 'sudo touch /etc/test',
    'printf data > file.txt', 'ls; rm notes.md', 'echo $(rm notes.md)',
    'cat `whoami`', 'pwd\nrm notes.md', 'bash script.sh',
    'python -c "print(1)"', 'rg --pre=script.py x', 'cat .env', 'date --set=tomorrow',
])
def test_risky_or_unclassified_commands_require_approval(command):
    assert dangerous_command(command)


@pytest.mark.parametrize('path', ['.env', '/.git/config', '/AGENT.md', '/skills/demo/SKILL.md', '/.ssh/id_rsa'])
def test_sensitive_file_changes_require_approval(path):
    assert sensitive_path(path)

