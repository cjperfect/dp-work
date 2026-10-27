"""个人服务配置、密钥存储及连接测试。"""
from src.infrastructure.sidecar.service import sidecar
import json
from typing import Literal
from jwcrypto import jwe
from sqlalchemy import func
from src.core.exceptions import ApiError
from src.core.responses import ApiCode
from src.infrastructure.database import session
from src.utils import credential_transport
from .repository import SettingsRepository
from .schemas import ServiceConfig

Kind = Literal["model", "asr"]


def seal(value: str, owner_id: int, kind: Kind) -> str:
    """使用服务端 RSA 密钥加密个人凭证。"""
    token = jwe.JWE(json.dumps({"owner": owner_id, "kind": kind, "key": value}).encode(),
                    protected={"alg": "RSA-OAEP-256", "enc": "A256GCM"})
    token.add_recipient(credential_transport.get_transport_key())
    return token.serialize(compact=True)


def unseal(value: str, owner_id: int, kind: Kind) -> str:
    """解密并校验个人凭证所属账号。"""
    token = jwe.JWE(algs=["RSA-OAEP-256", "A256GCM"])
    token.deserialize(value, key=credential_transport.get_transport_key())
    payload = json.loads(token.payload)
    if payload["owner"] != owner_id or payload["kind"] != kind:
        raise ValueError("凭证所属账号不匹配")
    return payload["key"]


async def runtime(owner_id: int, kind: Kind) -> dict | None:
    """解析启用的个人配置，仅供服务端执行使用。"""
    async with session.read_session() as conn:
        row = await SettingsRepository(conn).get(owner_id)
        data = getattr(row, f"{kind}_config", {}) if row else {}
        if not data.get("enabled"):
            return None
        encrypted = getattr(row, f"{kind}_key")
        if not encrypted:
            raise ApiError(ApiCode.PARAM_ERROR, "个人服务尚未配置 API Key，请前往设置补充。")
        return {**data, "api_key": unseal(encrypted, owner_id, kind)}




async def read(owner_id: int) -> dict:
    """返回个人配置与平台默认值，隐藏全部密钥。"""
    defaults = await sidecar("/settings/defaults")
    async with session.read_session() as conn:
        row = await SettingsRepository(conn).get(owner_id)
        result = {}
        for kind in ("model", "asr"):
            custom = getattr(row, f"{kind}_config", {}) if row else {}
            result[kind] = {**defaults[kind], **custom,
                "has_api_key": bool(getattr(row, f"{kind}_key", None)),
                "enabled": bool(custom.get("enabled")), "default": defaults[kind]}
        return result


async def save(owner_id: int, kind: Kind, body: ServiceConfig) -> dict:
    """保存个人覆盖配置，不修改平台环境变量。"""
    validate_kind(kind, body)
    async with session.transaction() as conn:
        row = await SettingsRepository(conn).ensure(owner_id)
        field = f"{kind}_key"
        previous_provider = getattr(row, f"{kind}_config", {}).get("provider")
        changed_provider = previous_provider is not None and previous_provider != body.provider
        if body.clear_api_key or (changed_provider and body.api_key is None):
            setattr(row, field, None)
        elif body.api_key is not None:
            setattr(row, field, seal(body.api_key.get_secret_value().strip(), owner_id, kind))
        if body.enabled and not getattr(row, field):
            raise ApiError(ApiCode.PARAM_ERROR, "启用个人配置前请填写 API Key。")
        setattr(row, f"{kind}_config", body.model_dump(exclude={"api_key", "clear_api_key"}))
        row.updated_at = func.clock_timestamp()
    return {"saved": True}


def validate_kind(kind: Kind, body: ServiceConfig):
    """校验配置与服务类型一致。"""
    if (kind == "asr") != (body.provider == "doubao"):
        raise ApiError(ApiCode.PARAM_ERROR, "服务商与配置类型不匹配。")


async def test(owner_id: int, kind: Kind, body: ServiceConfig) -> dict:
    """测试当前表单，不写入配置。"""
    validate_kind(kind, body)
    data = None
    if body.enabled:
        async with session.read_session() as conn:
            row = await SettingsRepository(conn).get(owner_id)
            encrypted = getattr(row, f"{kind}_key", None)
            previous_provider = getattr(row, f"{kind}_config", {}).get("provider") if row else None
            if previous_provider != body.provider:
                encrypted = None
            key = body.api_key.get_secret_value().strip() if body.api_key else (
                unseal(encrypted, owner_id, kind) if encrypted and not body.clear_api_key else "")
        if not key:
            raise ApiError(ApiCode.PARAM_ERROR, "请先填写 API Key。")
        data = {**body.model_dump(exclude={"api_key", "clear_api_key"}), "api_key": key}
    return await sidecar("/settings/test", {"kind": kind, "config": data})


async def asr_session(owner_id: int, meeting_id: str) -> dict:
    """验证会议归属并申请一次性语音连接票据。"""
    from src.modules.meetings import service as meetings
    workspace = await meetings.get(owner_id, meeting_id)
    if workspace.meeting.status != "active":
        raise ApiError(ApiCode.STATE_CONFLICT, "会议尚未开始或已结束。", 409)
    return await sidecar("/asr/sessions", {"meeting_id": meeting_id, "owner_id": owner_id,
                                         "runtime": await runtime(owner_id, "asr")})
