"""独立 Linux 实测：python tests/tools/sandbox_linux_smoke.py，无第三方 Python 依赖。"""
from pathlib import Path
import shlex
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.tools.isolation import isolated_command, sandbox_backend


class LinuxBoundaryTest(unittest.TestCase):
    def test_actual_bubblewrap_boundary(self):
        self.assertEqual(sandbox_backend(), 'linux', '必须使用真实 Bubblewrap，不能跳过')
        with TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / 'project'
            root.mkdir()
            secret = parent / 'secret'
            secret.write_text('private')
            (root / 'escape').symlink_to(secret)
            def execute(command):
                with isolated_command(root, '/bin/bash', command, {'PATH': '/usr/local/bin:/usr/bin:/bin', 'ARK_API_KEY': 'secret'}) as (args, env):
                    return subprocess.run(args, env=env, capture_output=True, text=True, timeout=5)
            good = execute('echo inside > note; cat note')
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertEqual(good.stdout.strip(), 'inside')
            for command in ('cat ' + shlex.quote(str(secret)), 'cat escape', 'echo bad > /etc/host-file'):
                self.assertNotEqual(execute(command).returncode, 0, command)
            # /tmp 是私有 tmpfs；绝对软链接可能写入同名临时路径，不能影响宿主文件。
            execute('echo bad > escape')
            self.assertEqual(secret.read_text(), 'private')
            env = execute('env').stdout
            self.assertNotIn('ARK_API_KEY=', env)
            self.assertNotIn('HOME=' + str(Path.home()) + '\n', env)
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                listener.listen()
                program = f'import socket;socket.create_connection(("127.0.0.1",{listener.getsockname()[1]}),.5)'
                self.assertNotEqual(execute('python -c ' + shlex.quote(program)).returncode, 0)
            self.assertNotEqual(execute('readlink /proc/self/ns/pid').stdout.strip(),
                                str(Path('/proc/self/ns/pid').readlink()))


if __name__ == '__main__':
    unittest.main()
