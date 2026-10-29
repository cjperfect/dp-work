"""Linux Bubblewrap：白名单挂载、独立命名空间、禁止网络。"""
from pathlib import Path
import shutil
import sys

from .isolation import IsolationUnavailable, bash_arguments


def linux_command(workspace, temporary, executable, command):
    """构造受限命令，不挂载整个宿主根目录或 /run。"""
    bwrap = shutil.which('bwrap')
    if not bwrap:
        raise IsolationUnavailable('未安装 Bubblewrap，命令未执行。')
    args = [bwrap, '--unshare-user', '--unshare-pid', '--unshare-net', '--unshare-ipc',
            '--unshare-uts', '--die-with-parent', '--new-session', '--cap-drop', 'ALL',
            '--disable-userns', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp']
    # 合并只读路径，避免 usr-merge 系统的 /bin、/lib 软链接重复挂载。
    roots = []
    for value in ('/usr', '/bin', '/sbin', '/lib', '/lib64', sys.base_prefix, sys.prefix):
        path = Path(value)
        if not path.exists():
            continue
        resolved = path.resolve()
        if not any(resolved.is_relative_to(root) for root in roots):
            roots.append(resolved)
    for path in roots:
        args += ['--ro-bind', str(path), str(path)]
    for value in ('/bin', '/sbin', '/lib', '/lib64'):
        path = Path(value)
        if path.is_symlink():
            args += ['--symlink', str(path.readlink()), value]
    for value in ('/etc/ld.so.cache', '/etc/localtime'):
        if Path(value).exists():
            args += ['--ro-bind', value, value]
    args += ['--bind', str(temporary), str(temporary), '--bind', str(workspace), str(workspace),
             '--remount-ro', '/', '--chdir', str(workspace), '--', *bash_arguments(executable, command)]
    return args
