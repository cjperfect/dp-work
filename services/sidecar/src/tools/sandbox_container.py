"""Windows 通过本机 Docker Linux 容器执行；宿主 Docker 权限不传给 Agent。"""
import asyncio
import logging
import math
import os
import re
import shutil
from tempfile import TemporaryDirectory
from uuid import uuid4

import anyio

from .isolation import IsolationUnavailable, validate_workspace

log = logging.getLogger(__name__)


def local_docker_endpoint():
    """只连接本机 Docker 引擎。"""
    return 'npipe:////./pipe/docker_engine' if os.name == 'nt' else 'unix:///var/run/docker.sock'


def container_command(workspace, image, name, timeout):
    """仅将授权目录映射到 /workspace，容器系统只读且无外部网络。"""
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
        raise IsolationUnavailable('AGENT_SANDBOX_IMAGE 必须是本机镜像的完整 sha256 ID。')
    if ',' in str(workspace):
        raise IsolationUnavailable('容器沙箱暂不支持包含逗号的项目路径。')
    return ['create', '--name', name, '--pull=never', '--init', '--network=none',
            '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
            '--pids-limit=128', '--memory=512m', '--memory-swap=512m', '--cpus=1',
            '--ulimit', 'nofile=1024:1024', '--ulimit', 'fsize=67108864:67108864',
            '--user=65532:65532', '--workdir=/workspace',
            '--mount', f'type=bind,source={workspace},target=/workspace',
            '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m,mode=1777',
            '--tmpfs', '/home/agent:rw,nosuid,nodev,size=32m,mode=1777',
            '--env', 'HOME=/home/agent', '--env', 'TMPDIR=/tmp',
            '--env', 'PATH=/usr/local/bin:/usr/bin:/bin',
            '--env', 'GIT_CONFIG_NOSYSTEM=1', '--env', 'GIT_CONFIG_GLOBAL=/dev/null',
            '--entrypoint=/usr/bin/timeout', image, '--signal=KILL',
            str(math.ceil(timeout + 2)), '/bin/bash', '--noprofile', '--norc', '-c']


async def docker_control(base, args, environment):
    """限时执行宿主控制命令，不经 Shell，也不接受模型提供 Docker 参数。"""
    process = await asyncio.create_subprocess_exec(*base, *args, env=environment,
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT)
    try:
        async with asyncio.timeout(10):
            output, _ = await process.communicate()
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()
    return process.returncode, output.decode('utf-8', errors='replace')[:2000]


async def execute_in_container(workspace, command, timeout, max_output_bytes, environment, runner, image):
    """创建、附着并强制清理容器；取消 CLI 也会清理容器中的进程。"""
    workspace = validate_workspace(workspace)
    docker = shutil.which('docker')
    if not docker:
        raise IsolationUnavailable('请安装并启动 Docker Desktop，切换为 Linux 容器。')
    name = 'dp-work-exec-' + uuid4().hex
    create = container_command(workspace, image, name, timeout) + [command]
    # 固定本机 daemon，不采用用户的远程 context；不把控制环境传入容器。
    endpoint = local_docker_endpoint()
    env = {key: value for key, value in environment.items()
           if key.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'}}
    with TemporaryDirectory(prefix='dp-work-docker-') as directory:
        base = [docker, '--host', endpoint, '--config', directory]
        try:
            code, output = await docker_control(base, create, env)
            if code:
                raise IsolationUnavailable('容器沙箱启动失败，请检查 Docker 的 Linux 容器模式、目录共享权限和本机镜像。\n' + output)
            return await runner(base + ['start', '--attach', name], workspace, env, timeout, max_output_bytes)
        finally:
            with anyio.CancelScope(shield=True):
                try:
                    code, output = await docker_control(base, ['rm', '--force', name], env)
                    if code and 'No such container' not in output:
                        log.error('命令容器清理失败 %s: %s', name, output)
                except (OSError, TimeoutError):
                    log.exception('命令容器清理失败 %s；容器内超时仍生效', name)
