from fastapi import APIRouter, Response
from fastapi.concurrency import run_in_threadpool

from src.utils.credential_transport import decrypt_password, public_encryption_key
from src.core.responses import ApiResponse, ok


from . import service
from .schemas import LoginIn, RefreshIn, RegisterIn

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get(
    "/encryption-key", response_model=ApiResponse[dict], summary="登录密码加密公钥"
)
def encryption_key(response: Response) -> ApiResponse[dict]:
    """获取密码传输公钥。"""
    response.headers["Cache-Control"] = "no-store"
    return ok(public_encryption_key())


@router.post(
    "/register",
    response_model=ApiResponse[dict],
    status_code=200,
    summary="用户名密码注册",
)
async def register(body: RegisterIn) -> ApiResponse[dict]:
    """注册用户。"""
    password = await run_in_threadpool(
        decrypt_password, body.encrypted_password, body.username, "register"
    )
    return ok(
        await service.register(body.username, password, body.department),
        message="注册成功",
    )


@router.post("/login", response_model=ApiResponse[dict], summary="登录签发 JWT")
async def login(body: LoginIn) -> ApiResponse[dict]:
    """验证账号并登录。"""
    password = await run_in_threadpool(
        decrypt_password, body.encrypted_password, body.username, "login"
    )
    return ok(await service.login(body.username, password), message="登录成功")


@router.post("/refresh", response_model=ApiResponse[dict], summary="刷新令牌")
async def refresh(body: RefreshIn) -> ApiResponse[dict]:
    """刷新访问令牌。"""
    return ok(await service.refresh(body.token), message="刷新成功")
