"""飞书官方 CLI 的固定命令适配。"""
import asyncio
import base64
import json
import hashlib
import os
from pathlib import Path
import re
import shutil
import sys
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse
from uuid import uuid4

from app.core.exceptions import ApiError
from app.core.responses import ApiCode

REPO_ROOT = Path(__file__).resolve().parents[5]
DATA_ROOT = Path(os.environ.get("DP_DATA_DIR") or REPO_ROOT / ".dp-work/data")
SYSTEM_HOME = Path.home()
CLI_PACKAGE = REPO_ROOT / "node_modules/@larksuite/cli/bin"
LOGIN_SCOPE = "auth:user.id:read offline_access"
ENV_KEYS = {"PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL", "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "NO_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR"}


def binary() -> str | None:
    """定位固定版本或显式配置的 CLI。"""
    name = "lark-cli.exe" if os.name == "nt" else "lark-cli"
    path = Path(os.environ.get("FEISHU_CLI_BIN") or CLI_PACKAGE / name)
    if path.is_file():
        return str(path.resolve())
    return shutil.which("lark-cli") if not os.environ.get("FEISHU_CLI_BIN") else None


def profile(owner_id: int) -> Path:
    """按当前平台用户隔离 CLI 配置。"""
    if type(owner_id) is not int or owner_id < 1:
        raise ValueError("无效的用户 ID")
    path = DATA_ROOT.parent / "connectors/feishu" / str(owner_id)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def _copy_encrypted(source: Path, target: Path) -> None:
    """只复制已存在的密文，不覆盖当前目录中的新凭证。"""
    if not source.is_file() or target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = None
    try:
        with NamedTemporaryFile(dir=target.parent, prefix=".credential-", delete=False) as stream:
            staging = Path(stream.name)
            stream.write(source.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(staging, target)
        except FileExistsError:
            pass
    finally:
        if staging:
            staging.unlink(missing_ok=True)


def credentials_directory(owner_id: int) -> Path:
    """定位当前账号的 CLI 凭证密文目录。"""
    root = profile(owner_id) / "credentials"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if sys.platform == "darwin":
        return root / "Library/Application Support/lark-cli"
    return root / "lark-cli"


def migrate_credentials(owner_id: int) -> None:
    """迁移本账号引用的旧密文，不读取 Token 或搬走其他账号数据。"""
    if sys.platform == "win32":
        return  # 官方 Windows CLI 使用 DPAPI 注册表，不能用 HOME 重定向。
    directory = profile(owner_id)
    marker = directory / ".credentials-migrated-v1"
    if marker.exists():
        return
    settings = directory / "config.json"
    if not settings.is_file():
        return
    value = json.loads(settings.read_text(encoding="utf-8"))
    names = set()
    for app in value.get("apps", []):
        app_id = app.get("appId", "")
        if not isinstance(app_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", app_id):
            continue
        names.add(f"appsecret_{app_id}.enc")
        names.add(f"tat_v1_{hashlib.sha256(app_id.encode()).hexdigest()}.enc")
        for user in app.get("users", []):
            user_id = user.get("userOpenId", "")
            if isinstance(user_id, str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", user_id):
                names.add(f"{app_id}_{user_id}.enc")
    source = (SYSTEM_HOME / "Library/Application Support/lark-cli" if sys.platform == "darwin"
              else SYSTEM_HOME / ".local/share/lark-cli")
    target = credentials_directory(owner_id)
    matching = [name for name in names if (source / name).is_file()]
    if matching:
        # 已使用文件主密钥的旧环境保持原有保护方式，不主动降级系统钥匙串。
        for name in ("master.key.file", "master.key"):
            _copy_encrypted(source / name, target / name)
        for name in matching:
            _copy_encrypted(source / name, target / name)
    marker.touch(mode=0o600, exist_ok=True)


def environment(owner_id: int) -> dict[str, str]:
    """隔离 CLI 的配置、凭证目录与运行环境。"""
    migrate_credentials(owner_id)
    credentials = profile(owner_id) / "credentials"
    credentials.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = {**{key: value for key, value in os.environ.items() if key.upper() in ENV_KEYS},
           "LARKSUITE_CLI_CONFIG_DIR": str(profile(owner_id)),
           "LARKSUITE_CLI_DATA_DIR": str(credentials),
           "LARKSUITE_CLI_NO_UPDATE_NOTIFIER": "1",
           "LARKSUITE_CLI_NO_SKILLS_NOTIFIER": "1"}
    if sys.platform != "win32":
        env["HOME"] = str(credentials)
    return env


def read_connection(owner_id: int) -> dict:
    """读取上次验证记录，凭证仍由 CLI 加密保存。"""
    try:
        value = json.loads((profile(owner_id) / "connection.json").read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, ValueError, UnicodeDecodeError):
        return {}


def save_connection(owner_id: int, record: dict) -> None:
    """原子保存账号绑定和验证时间，不保存明文 Token。"""
    target = profile(owner_id) / "connection.json"
    staging = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                prefix=".connection-", suffix=".tmp", delete=False) as stream:
            staging = Path(stream.name)
            json.dump(record, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staging, target)
    finally:
        if staging:
            staging.unlink(missing_ok=True)


def safe_url(value: str) -> bool:
    """只接受飞书官方 HTTPS 授权链接。"""
    parsed = urlparse(value)
    host = parsed.hostname or ""
    domains = ("feishu.cn", "larksuite.com", "larkoffice.com")
    return (parsed.scheme == "https" and not parsed.username and not parsed.password
            and any(host == domain or host.endswith("." + domain) for domain in domains))


def decode(output: bytes) -> dict:
    """提取 CLI 的 JSON 成功响应。"""
    try:
        value = json.loads(output)
        if isinstance(value, dict) and value.get("ok") is not False:
            return value.get("data", value) if isinstance(value.get("data", value), dict) else value
    except (ValueError, UnicodeDecodeError):
        pass
    raise ApiError(ApiCode.INTERNAL_ERROR, "飞书 CLI 返回数据无效，请重试。", 502)


async def terminate(process) -> None:
    """终止后台 CLI，避免取消或超时后残留进程。"""
    if process.returncode is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), 2)
    except TimeoutError:
        process.kill()
        await process.wait()


async def spawn(owner_id: int, *arguments: str, cwd: Path | None = None):
    """以参数数组启动 CLI，不经过 Shell。"""
    executable = binary()
    if executable is None:
        raise ApiError(ApiCode.STATE_CONFLICT, "飞书 CLI 尚未安装，请运行 pnpm setup:feishu-cli。", 409)
    return await asyncio.create_subprocess_exec(executable, *arguments, cwd=cwd or profile(owner_id),
        env=environment(owner_id), stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, limit=262144)


async def run(owner_id: int, *arguments: str, timeout: float = 12, cwd: Path | None = None) -> dict:
    """执行固定 CLI 命令并隐藏原始诊断输出。"""
    process = await spawn(owner_id, *arguments, cwd=cwd)
    try:
        stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout)
        if process.returncode:
            raise ApiError(ApiCode.STATE_CONFLICT, "飞书 CLI 操作失败，请检查应用配置、授权及网络。", 409)
        if len(stdout) > 1024 * 1024:
            raise ApiError(ApiCode.INTERNAL_ERROR, "飞书 CLI 响应过大。", 502)
        return decode(stdout)
    except TimeoutError as cause:
        raise ApiError(ApiCode.STATE_CONFLICT, "飞书 CLI 请求超时，请重试。", 504) from cause
    finally:
        await terminate(process)


async def qrcode(owner_id: int, url: str) -> str | None:
    """生成授权二维码，不将文件路径暴露给页面。"""
    if not safe_url(url):
        return None
    folder = DATA_ROOT.parent / "temp/connectors/feishu" / str(owner_id) / uuid4().hex
    folder.mkdir(parents=True, mode=0o700)
    filename = "authorization.png"
    path = folder / filename
    try:
        await run(owner_id, "auth", "qrcode", url, "--output", filename, timeout=8, cwd=folder)
        data = path.read_bytes()
        if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) < 262144:
            return "data:image/png;base64," + base64.b64encode(data).decode()
    except (ApiError, OSError):
        pass
    finally:
        path.unlink(missing_ok=True)
        try:
            folder.rmdir()
        except OSError:
            pass
    return None


async def configure(owner_id: int, on_url) -> None:
    """运行官方浏览器配置流程，仅提取授权链接。"""
    process = await spawn(owner_id, "config", "init", "--new", "--brand", "feishu", "--lang", "zh")
    async def consume(stream):
        async for line in stream:
            for value in re.findall(r"https://[^\s<>\"\x1b]+", line.decode("utf-8", errors="replace")):
                if safe_url(value) and "document/" not in value:
                    await on_url(value)
    try:
        async with asyncio.timeout(600):
            await asyncio.gather(consume(process.stdout), consume(process.stderr))
            if await process.wait():
                raise ApiError(ApiCode.STATE_CONFLICT, "飞书应用配置未完成，请重试；如需审批，请联系管理员。", 409)
    finally:
        await terminate(process)
