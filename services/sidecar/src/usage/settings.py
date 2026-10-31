"""当前账号的本机单价与任务预算配置。"""
import json
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from .. import config
from ..providers import local_settings

Money = Annotated[Decimal, Field(ge=0, le=1_000_000_000, allow_inf_nan=False, max_digits=24, decimal_places=12)]


class ModelPrice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    input: Money
    output: Money
    cached_input: Money | None = None


class UsageSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = False
    currency: Annotated[str, StringConstraints(pattern=r'^[A-Z]{3}$')] = 'CNY'
    token_limit: int = Field(default=0, ge=0, le=1_000_000_000, strict=True)
    cost_limit: Money = Decimal(0)
    asr_price_per_hour: Money | None = None
    model_prices: dict[str, ModelPrice] = Field(default_factory=dict, max_length=100)

    @field_validator('model_prices')
    @classmethod
    def validate_models(cls, value):
        """拒绝空模型标识和重复归一化标识。"""
        if any(not key.strip() or key != key.strip() or len(key) > 128 for key in value):
            raise ValueError('请输入有效的模型 ID，且不能包含首尾空格。')
        return value


def defaults():
    """环境变量作为未启用个人设置时的默认值。"""
    return UsageSettings(currency=config.AGENT_COST_CURRENCY, token_limit=config.AGENT_RUN_TOKEN_LIMIT,
        cost_limit=config.AGENT_RUN_COST_LIMIT, model_prices=json.loads(config.AGENT_MODEL_PRICES),
        asr_price_per_hour=config.ASR_PRICE_PER_HOUR or None).model_dump(mode='json', exclude_none=True)


def effective(owner=None):
    """返回当前账号生效的单价与预算，不修改全局配置。"""
    if owner is not None:
        with local_settings.LOCK:
            value = local_settings.load(owner).get('usage')
        if value is not None:
            result = UsageSettings.model_validate(value)
            if result.enabled:
                return result.model_dump(mode='json', exclude_none=True)
    return defaults()


def read(owner):
    """读取保存值及环境默认值。"""
    platform = defaults()
    with local_settings.LOCK:
        stored = local_settings.load(owner).get('usage')
    value = UsageSettings.model_validate(stored if stored is not None else platform)
    return {**value.model_dump(mode='json', exclude_none=True), 'default': platform}


def save(owner, body):
    """校验后原子保存，保留模型及 ASR 的其他设置。"""
    value = UsageSettings.model_validate(body)
    with local_settings.LOCK:
        if value.enabled and value.cost_limit:
            personal = local_settings.runtime(owner, 'model')
            model = personal.model if personal else config.ARK_MODEL
            if not model or model not in value.model_prices:
                raise ValueError('启用费用预算前，请先填写当前模型的输入和输出单价。')
        data = local_settings.load(owner)
        data.update(schema_version=1, usage=value.model_dump(mode='json', exclude_none=True))
        local_settings.atomic(local_settings.paths(owner)[0], json.dumps(data, ensure_ascii=False, indent=2).encode())
    return read(owner)
