"""平台依赖失败、容器生命周期及审批边界回归。"""
import asyncio
import os
from pathlib import Path

import pytest

from src.tools import isolation, sandbox_container, sandbox_linux
from src.tools.shell import execute_command, run_process


@pytest.mark.parametrize('platform', ['linux', 'win32', 'unsupported'])
def test_missing_backend_fails_closed(monkeypatch, tmp_path, platform):
    monkeypatch.setattr(isolation.sys, 'platform', platform)
    monkeypatch.setattr(isolation.shutil, 'which', lambda _: None)
    assert isolation.sandbox_backend() is None
    with pytest.raises(isolation.IsolationUnavailable):
        with isolation.isolated_command(tmp_path, '/bin/bash', 'touch escaped', {}):
            pytest.fail('不能启动宿主命令')
    assert not (tmp_path / 'escaped').exists()


@pytest.mark.parametrize('path', [Path.home(), Path(Path.home().anchor), Path('/usr')])
def test_broad_workspaces_are_rejected(path):
    if not path.exists():
        pytest.skip('此系统无该路径')
    with pytest.raises(isolation.IsolationUnavailable):
        isolation.validate_workspace(path)


def test_linux_plan_has_only_allowlisted_mounts(monkeypatch, tmp_path):
    monkeypatch.setattr(sandbox_linux.shutil, 'which', lambda _: '/usr/bin/bwrap')
    args = sandbox_linux.linux_command(tmp_path / 'project', tmp_path / 'temp', '/bin/bash', 'pwd')
    assert all(flag in args for flag in ('--unshare-user', '--unshare-net', '--unshare-pid', '--disable-userns', '--die-with-parent', '--new-session'))
    mounts = [args[i + 1:i + 3] for i, arg in enumerate(args) if arg == '--bind']
    assert mounts == [[str(tmp_path / 'temp')] * 2, [str(tmp_path / 'project')] * 2]
    assert '/' not in [args[i + 1] for i, arg in enumerate(args) if arg in ('--bind', '--ro-bind')]


def test_container_does_not_accept_mutable_or_option_image(tmp_path):
    for image in ('python:latest', '--privileged', '', 'sha256:abc'):
        with pytest.raises(isolation.IsolationUnavailable):
            sandbox_container.container_command(tmp_path, image, 'test', 1)


@pytest.mark.parametrize('outcome', ['success', 'create_error', 'timeout', 'cancel'])
def test_container_is_removed_for_every_terminal_path(monkeypatch, tmp_path, outcome):
    calls = []
    entered = asyncio.Event()
    async def control(base, args, env):
        calls.append(args)
        assert 'ARK_API_KEY' not in env and 'DOCKER_HOST' not in env
        return (1, 'fixture') if args[0] == 'create' and outcome == 'create_error' else (0, '')
    async def runner(*_):
        entered.set()
        if outcome == 'timeout':
            raise TimeoutError()
        if outcome == 'cancel':
            await asyncio.Event().wait()
        return 'done'
    monkeypatch.setattr(sandbox_container, 'docker_control', control)
    monkeypatch.setattr(sandbox_container.shutil, 'which', lambda _: '/usr/bin/docker')
    async def case():
        task = asyncio.create_task(sandbox_container.execute_in_container(tmp_path, 'pwd', 1, 32000,
            {'ARK_API_KEY': 'secret', 'DOCKER_HOST': 'remote'}, runner, 'sha256:' + 'a' * 64))
        if outcome == 'cancel':
            await entered.wait()
            task.cancel()
        if outcome in ('create_error', 'timeout', 'cancel'):
            error = {'create_error': isolation.IsolationUnavailable, 'timeout': TimeoutError, 'cancel': asyncio.CancelledError}[outcome]
            with pytest.raises(error):
                await task
        else:
            assert await task == 'done'
    asyncio.run(case())
    assert calls[-1][:2] == ['rm', '--force']
    assert calls[0][2] == calls[-1][2]


@pytest.mark.skipif(not os.environ.get('DP_TEST_SANDBOX_IMAGE'), reason='需显式指定本机测试镜像和 Docker endpoint')
def test_real_linux_container_boundary_and_cancellation(monkeypatch, tmp_path):
    """可在 Docker Desktop 上实测容器后端；不冒充 Windows 原生验证。"""
    monkeypatch.setattr(sandbox_container, 'local_docker_endpoint', lambda: os.environ['DP_TEST_DOCKER_HOST'])
    root = tmp_path / 'project'
    root.mkdir(mode=0o777)
    root.chmod(0o777)
    secret = tmp_path / 'secret'
    secret.write_text('outside-secret')
    (root / 'escape').symlink_to(secret)
    image = os.environ['DP_TEST_SANDBOX_IMAGE']
    async def execute(command, timeout=5):
        return await sandbox_container.execute_in_container(root, command, timeout, 32000,
            {'PATH': os.environ['PATH'], 'ARK_API_KEY': 'fixture', 'SSH_AUTH_SOCK': 'fixture'}, run_process, image)
    async def case():
        good = await execute('echo inside > note; cat note; pwd')
        assert good.exit_code == 0 and good.output == 'inside\n/workspace\n'
        for command in ('cat escape', 'echo bad > /etc/host-file', 'test -e /var/run/docker.sock',
                        'python -c "import socket;socket.create_connection((\'1.1.1.1\',443),.5)"'):
            assert (await execute(command)).exit_code != 0
        env = await execute('env')
        assert 'ARK_API_KEY' not in env.output and 'SSH_AUTH_SOCK' not in env.output
        timeout = await execute('sleep 20', .2)
        assert timeout.exit_code == 124
        task = asyncio.create_task(execute('echo started > running; sleep 20; echo leaked > leaked'))
        for _ in range(100):
            if (root / 'running').exists():
                break
            await asyncio.sleep(.05)
        assert (root / 'running').exists()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not (root / 'leaked').exists()
    asyncio.run(case())
    assert secret.read_text() == 'outside-secret'
