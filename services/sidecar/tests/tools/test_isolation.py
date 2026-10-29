"""验证命令沙箱的真实文件与网络边界。"""
import asyncio
import os
import shlex
import sys
import socket
import pytest
from src.tools.shell import execute_command
from src.tools import isolation


@pytest.mark.skipif(sys.platform != 'darwin', reason='macOS 系统沙箱')
def test_commands_cannot_read_or_write_outside_workspace_or_follow_symlink(tmp_path):
    root=tmp_path/'project'; root.mkdir()
    secret=tmp_path/'secret.txt';secret.write_text('private-fixture')
    outside=tmp_path/'outside.txt'
    (root/'link').symlink_to(secret)
    async def case():
        async def execute(command): return await execute_command(root,command,3,32000,{'PATH':'/usr/bin:/bin','ARK_API_KEY':'must-not-inherit','SSH_AUTH_SOCK':'must-not-inherit'})
        good=await execute('echo workspace > note.txt; cat note.txt')
        assert good.exit_code==0 and good.output.strip()=='workspace'
        assert (await execute('cat '+shlex.quote(str(secret)))).exit_code != 0
        assert (await execute('cat link')).exit_code != 0
        assert (await execute('echo modified > '+shlex.quote(str(outside)))).exit_code != 0
        assert (await execute('echo modified > link')).exit_code != 0
        assert secret.read_text()=='private-fixture' and not outside.exists()
        env=await execute('env')
        assert 'ARK_API_KEY' not in env.output and 'SSH_AUTH_SOCK' not in env.output
        assert 'HOME='+str(os.path.expanduser('~'))+'\n' not in env.output
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));listener.listen()
            result=await execute('/usr/bin/curl --max-time 1 http://127.0.0.1:'+str(listener.getsockname()[1]))
            assert result.exit_code != 0
            listener.setblocking(False)
            with pytest.raises(BlockingIOError): listener.accept()
    asyncio.run(case())


def test_missing_isolation_never_runs_host_command(monkeypatch,tmp_path):
    monkeypatch.setattr(isolation.sys,'platform','unsupported')
    async def case():
        result=await execute_command(tmp_path,'echo escaped > escape.txt',3,32000,{'PATH':'/usr/bin:/bin'})
        assert result.exit_code==126 and not (tmp_path/'escape.txt').exists()
    asyncio.run(case())


@pytest.mark.skipif(isolation.sandbox_backend() not in ('macos', 'linux'), reason='需要真实原生沙箱')
def test_hard_limits_and_untrusted_path_cannot_be_relaxed(tmp_path):
    impostor = tmp_path / 'ls'
    impostor.write_text('#!/bin/bash\necho bypassed > marker\n')
    impostor.chmod(0o755)
    async def case():
        result = await execute_command(tmp_path, 'ls; ulimit -H -n; ulimit -n 4096', 3, 32000,
                                       {'PATH': str(tmp_path) + ':/usr/bin:/bin'})
        assert result.exit_code != 0
        assert '256' in result.output
        assert not (tmp_path / 'marker').exists()
    asyncio.run(case())
