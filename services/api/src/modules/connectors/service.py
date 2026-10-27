"""飞书授权任务与登录状态。"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from src.core.exceptions import ApiError
from src.core.responses import ApiCode
from . import cli


@dataclass
class Authorization:
    action: str
    state: str = "starting"
    url: str | None = None
    qr_code: str | None = None
    message: str | None = None
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(minutes=10))
    task: asyncio.Task | None = None

    def public(self) -> dict:
        """只返回页面所需的授权信息。"""
        active = self.state in ("starting", "waiting")
        return dict(action=self.action, state=self.state, url=self.url if active else None,
                    qr_code=self.qr_code if active else None, message=self.message,
                    expires_at=self.expires_at.isoformat())


_jobs: dict[int, Authorization] = {}


async def status(owner_id: int, verify: bool = False) -> dict:
    """查询当前用户 CLI 与用户身份状态。"""
    result = dict(installed=cli.binary() is not None, configured=False,
                  connected=False, verified=False, account=None, last_verified_at=None, flow=None)
    job = _jobs.get(owner_id)
    if job:
        result["flow"] = job.public()
    if not result["installed"] or not (cli.profile(owner_id) / "config.json").is_file():
        return result
    result["configured"] = True
    arguments = ["auth", "status", "--json"]
    if verify:
        arguments.append("--verify")
    data = await cli.run(owner_id, *arguments, timeout=20 if verify else 8)
    user = data.get("identities", {}).get("user", {})
    if not verify and user.get("tokenStatus") == "needs_refresh":
        data = await cli.run(owner_id, "auth", "status", "--json", "--verify", timeout=20)
        user = data.get("identities", {}).get("user", {})
        verify = True
    available = user.get("available") is True and user.get("tokenStatus") != "expired"
    verified = available and user.get("verified", data.get("verified")) is True
    previous = cli.read_connection(owner_id)
    app_id, user_id = data.get("appId"), user.get("openId")
    same_account = (isinstance(app_id, str) and bool(app_id) and isinstance(user_id, str) and bool(user_id)
                    and previous.get("app_id") == app_id and previous.get("user_id") == user_id)
    last_verified = previous.get("last_verified_at") if same_account else None
    if verified and isinstance(app_id, str) and app_id and isinstance(user_id, str) and user_id:
        last_verified = datetime.now(timezone.utc).isoformat()
        cli.save_connection(owner_id, dict(app_id=app_id, user_id=user_id,
            account=user.get("userName"), last_verified_at=last_verified))
    if not verify and available and same_account and last_verified:
        verified = True
    result.update(connected=available and (verified if verify else True), verified=verified,
                  account=user.get("userName") if available else None,
                  last_verified_at=last_verified if available else None)
    return result


async def _authorize(owner_id: int, job: Authorization) -> None:
    """等待用户完成网页操作，凭证只由 CLI 接收和保存。"""
    async def on_url(url: str):
        if job.url is not None:
            return
        if not cli.safe_url(url):
            raise ApiError(ApiCode.INTERNAL_ERROR, "授权地址无效。", 502)
        job.url = url
        job.state = "waiting"
        job.qr_code = await cli.qrcode(owner_id, url)
    try:
        if job.action == "configure":
            await cli.configure(owner_id, on_url)
            job.message = "应用配置完成，请继续点击授权登录。"
        else:
            data = await cli.run(owner_id, "auth", "login", "--scope", cli.LOGIN_SCOPE, "--no-wait", "--json")
            url, code = data.get("verification_url"), data.get("device_code")
            if not isinstance(url, str) or not isinstance(code, str) or not code:
                raise ApiError(ApiCode.INTERNAL_ERROR, "飞书未返回有效授权信息。", 502)
            await on_url(url)
            duration = min(max(int(data.get("expires_in", 300)), 30), 600)
            job.expires_at = datetime.now(timezone.utc) + timedelta(seconds=duration)
            await cli.run(owner_id, "auth", "login", "--device-code", code, "--json", timeout=duration + 5)
            checked = await status(owner_id, verify=True)
            if not checked["connected"]:
                raise ApiError(ApiCode.STATE_CONFLICT, "授权已结束但身份验证未通过，请重新验证或授权。", 409)
            job.message = "授权完成，飞书用户身份验证通过。"
        job.state = "completed"
    except asyncio.CancelledError:
        job.state = "cancelled"
        job.message = "授权已取消。"
        raise
    except TimeoutError:
        job.state = "failed"
        job.message = "授权已超时，请重新开始。"
    except Exception as cause:
        job.state = "failed"
        job.message = cause.message if isinstance(cause, ApiError) else "飞书授权失败，请检查网络和应用权限后重试。"
    finally:
        job.url = None
        job.qr_code = None


async def start(owner_id: int, action: str) -> dict:
    """启动用户主动选择的配置或授权操作。"""
    if cli.binary() is None:
        raise ApiError(ApiCode.STATE_CONFLICT, "飞书 CLI 尚未安装，请运行 pnpm setup:feishu-cli。", 409)
    current = _jobs.get(owner_id)
    if current and current.task and not current.task.done():
        raise ApiError(ApiCode.STATE_CONFLICT, "已有授权流程进行中，请先完成或取消。", 409)
    configured = (cli.profile(owner_id) / "config.json").is_file()
    if action == "configure" and configured:
        raise ApiError(ApiCode.STATE_CONFLICT, "应用已配置，请直接授权登录。", 409)
    if action == "login" and not configured:
        raise ApiError(ApiCode.STATE_CONFLICT, "请先配置飞书应用。", 409)
    job = Authorization(action=action)
    _jobs[owner_id] = job
    job.task = asyncio.create_task(_authorize(owner_id, job))
    return job.public()


async def cancel(owner_id: int) -> None:
    """取消当前用户的待完成授权。"""
    job = _jobs.get(owner_id)
    if job and job.task and not job.task.done():
        job.task.cancel()
        await asyncio.gather(job.task, return_exceptions=True)
    _jobs.pop(owner_id, None)


async def logout(owner_id: int) -> None:
    """断开本机登录态，保留应用配置。"""
    await cancel(owner_id)
    await cli.run(owner_id, "auth", "logout", "--json")
    (cli.profile(owner_id) / "connection.json").unlink(missing_ok=True)


async def shutdown() -> None:
    """服务关闭时回收待授权进程。"""
    for owner_id in list(_jobs):
        await cancel(owner_id)
