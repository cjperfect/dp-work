"""命令进程的系统级隔离；不可用时禁止执行，不降级到宿主 Bash。"""
import json
import os
import re
import shutil
from pathlib import Path
import sys
from contextlib import contextmanager
from tempfile import TemporaryDirectory


class IsolationUnavailable(Exception):
    pass


def sandbox_backend():
    """选择平台后端；这里只检测依赖，实际启动失败仍禁止降级。"""
    if sys.platform == 'darwin' and Path('/usr/bin/sandbox-exec').is_file():
        return 'macos'
    if sys.platform == 'linux' and shutil.which('bwrap'):
        return 'linux'
    if sys.platform == 'win32' and shutil.which('docker'):
        from .. import config
        if re.fullmatch(r'sha256:[0-9a-f]{64}', config.AGENT_SANDBOX_IMAGE):
            return 'container'
    return None


def validate_workspace(workspace):
    """不授权整个磁盘、主目录、系统目录或它们的父目录。"""
    try:
        workspace = Path(workspace).resolve(strict=True)
    except (OSError, ValueError) as cause:
        raise IsolationUnavailable('工作目录不可用，命令未执行。') from cause
    protected = [Path.home()]
    protected += [Path(value) for value in ('/bin', '/sbin', '/usr', '/etc', '/proc', '/sys', '/dev', '/System', '/Library', '/opt/homebrew') if os.name != 'nt']
    protected += [Path(os.environ[key]) for key in ('SYSTEMROOT', 'WINDIR', 'ProgramFiles', 'ProgramFiles(x86)') if os.environ.get(key)]
    if (not workspace.is_dir() or workspace == Path(workspace.anchor)
            or any(path.resolve().is_relative_to(workspace) for path in protected)
            or any(workspace.is_relative_to(path.resolve()) for path in protected[1:])):
        raise IsolationUnavailable('不能将磁盘根目录、用户主目录或系统目录作为命令执行范围。')
    if any(ord(char) < 32 for char in str(workspace)):
        raise IsolationUnavailable('目录包含不支持的控制字符，命令未执行。')
    return workspace


def literal(path):
    value = str(Path(path).resolve())
    if any(ord(char) < 32 for char in value):
        raise IsolationUnavailable('目录包含不支持的控制字符，命令未执行。')
    return json.dumps(value, ensure_ascii=False)


def bash_arguments(executable, command):
    """在启动用户命令前降低硬限制，子进程不能自行恢复上限。"""
    limits = 'ulimit -c 0 && ulimit -n 256 && ulimit -f 65536 && ulimit -t 30 && exec "$@"'
    return [executable, '--noprofile', '--norc', '-c', limits, 'dp-work-sandbox',
            executable, '--noprofile', '--norc', '-c', command]


def mac_profile(workspace, temporary):
    """仅授权工作目录和本次临时目录；其余业务文件与网络默认拒绝。"""
    readable = ['/bin', '/sbin', '/usr', '/System', '/Library', '/opt/homebrew',
                '/private/etc', '/private/var/db/dyld', '/private/var/db/timezone', sys.base_prefix, sys.prefix]
    rules = ['(version 1)', '(deny default)', '(import "dyld-support.sb")',
             '(allow syscall*)', '(allow process-exec)', '(allow process-fork)',
             '(allow sysctl-read)', '(allow file-read-metadata file-test-existence)',
             '(allow file-read* (literal "/dev/null") (literal "/dev/urandom") (literal "/dev/random"))',
             '(allow file-write* (literal "/dev/null"))']
    for path in readable:
        if Path(path).exists(): rules.append(f'(allow file-read* file-map-executable (subpath {literal(path)}))')
    for path in (workspace, temporary):
        rules.append(f'(allow file-read* file-write* file-map-executable (subpath {literal(path)}))')
    return '\n'.join(rules)


@contextmanager
def isolated_command(workspace, executable, command, environment):
    """为每次命令分配临时 HOME，并返回受限启动参数。"""
    backend = sandbox_backend()
    if backend not in ('macos', 'linux'):
        raise IsolationUnavailable('命令沙箱不可用。Linux 需要 Bubblewrap；Windows 需要 Docker Desktop（Linux 容器）及 AGENT_SANDBOX_IMAGE；不会降级执行宿主命令。')
    workspace = validate_workspace(workspace)
    with TemporaryDirectory(prefix='dp-work-exec-') as directory:
        temporary = Path(directory).resolve()
        home = temporary / 'home'
        home.mkdir(mode=0o700)
        allowed = {'PATH', 'LANG', 'LC_ALL', 'LC_CTYPE', 'SYSTEMROOT', 'WINDIR', 'COMSPEC'}
        env = {key: value for key, value in environment.items() if key.upper() in allowed}
        # 不允许项目中的同名程序通过 PATH 伪装成免审批的只读命令。
        env['PATH'] = '/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin' + (':/opt/homebrew/bin' if backend == 'macos' else '')
        env.update(HOME=str(home), TMPDIR=str(temporary), TMP=str(temporary), TEMP=str(temporary),
                   XDG_CONFIG_HOME=str(home / '.config'), XDG_CACHE_HOME=str(home / '.cache'),
                   GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null')
        if backend == 'linux':
            from .sandbox_linux import linux_command
            args = linux_command(workspace, temporary, executable, command)
        else:
            args = ['/usr/bin/sandbox-exec', '-p', mac_profile(workspace, temporary),
                    *bash_arguments(executable, command)]
        yield args, env
