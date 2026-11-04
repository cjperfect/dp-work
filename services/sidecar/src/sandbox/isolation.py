"""命令进程的系统级隔离；不可用时禁止执行，不降级到宿主 Bash。"""
import json
import os
import re
import shlex
import shutil
from pathlib import Path
import sys
from contextlib import contextmanager
from tempfile import TemporaryDirectory


class IsolationUnavailable(Exception):
    pass


def runtime_paths():
    """桌面版使用 Electron Node；独立开发使用 PATH 中的 Node。"""
    root = Path(__file__).resolve().parents[4]
    cli = Path(os.environ.get('DP_SANDBOX_CLI') or (
        Path(sys.executable).parent / 'sandbox-runtime/node_modules/@anthropic-ai/sandbox-runtime/dist/cli.js'
        if getattr(sys, 'frozen', False) else
        root / 'apps/desktop/node_modules/@anthropic-ai/sandbox-runtime/dist/cli.js'))
    node = os.environ.get('DP_SANDBOX_NODE') or shutil.which('node')
    if not node or not Path(node).is_file() or not cli.is_file():
        raise IsolationUnavailable('Anthropic Sandbox Runtime 未安装，请执行 pnpm install 并使用桌面端启动。')
    return str(Path(node).resolve()), str(cli.resolve())


def sandbox_backend():
    """只选择已安装的隔离后端，启动失败时不降级执行。"""
    if sys.platform in ('darwin', 'linux'):
        try:
            runtime_paths()
        except IsolationUnavailable:
            return None
        if sys.platform == 'darwin' and Path('/usr/bin/sandbox-exec').is_file():
            return 'macos'
        if sys.platform == 'linux' and all(shutil.which(name) for name in ('bwrap', 'socat', 'rg')):
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


def bash_arguments(executable, command):
    """在启动用户命令前降低硬限制，子进程不能自行恢复上限。"""
    limits = 'ulimit -c 0 && ulimit -n 256 && ulimit -f 65536 && ulimit -t 30 && exec "$@"'
    return [executable, '--noprofile', '--norc', '-c', limits, 'dp-work-sandbox',
            executable, '--noprofile', '--norc', '-c', command]


def runtime_settings(workspace, temporary):
    """拒绝宿主读取后，仅开放工作目录、临时目录及系统运行库。"""
    readable = [workspace, temporary]
    readable += [Path(value) for value in (
        '/bin', '/sbin', '/usr', '/lib', '/lib64', '/System', '/Library',
        '/opt/homebrew', '/private/etc', '/private/var/db/dyld',
        '/private/var/db/timezone', '/etc/ld.so.cache', '/etc/localtime',
        '/dev/null', '/dev/urandom', '/dev/random', sys.base_prefix, sys.prefix,
    ) if Path(value).exists()]
    literal = lambda path: {'path': str(Path(path).resolve()), 'literal': True}
    return {
        'network': {'allowedDomains': [], 'deniedDomains': ['*'],
                    'allowUnixSockets': [], 'allowLocalBinding': False},
        'filesystem': {'denyRead': [literal('/')],
                       'allowRead': [literal(path) for path in readable],
                       'allowWrite': [literal(workspace), literal(temporary)], 'denyWrite': []},
        'enableWeakerNestedSandbox': False,
        'enableWeakerNetworkIsolation': False,
        'allowNestedUserNamespaces': False,
    }


@contextmanager
def isolated_command(workspace, executable, command, environment):
    """为每次命令分配临时 HOME，并返回受限启动参数。"""
    backend = sandbox_backend()
    if backend not in ('macos', 'linux'):
        raise IsolationUnavailable('命令沙箱不可用。需要 Anthropic Sandbox Runtime；Linux 还需要 Bubblewrap、socat 和 ripgrep。不会降级执行宿主命令。')
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
        node, cli = runtime_paths()
        settings = temporary / 'settings.json'
        settings.write_text(json.dumps(runtime_settings(workspace, temporary)), encoding='utf-8')
        settings.chmod(0o600)
        # 只启动可信 Runtime 时启用 Electron Node 模式；不继承 NODE_OPTIONS 等宿主配置。
        env['ELECTRON_RUN_AS_NODE'] = '1'
        args = [node, cli, '--settings', str(settings), '-c',
                shlex.join(bash_arguments(executable, command))]
        yield args, env
