"""按任务职责选择环境模型；所有档位共用同一服务地址和凭证。"""
import logging
from dataclasses import replace
from enum import StrEnum

from ... import config
from .schemas import ModelError, ModelSettings

log = logging.getLogger(__name__)


class ModelTier(StrEnum):
    LITE = "lite"
    DEFAULT = "default"
    STRONG = "strong"


TASK_MODEL_MAP = {
    "title": ModelTier.LITE,
    "memory_extract": ModelTier.LITE,
    "memory_consolidate": ModelTier.DEFAULT,
    "minutes": ModelTier.DEFAULT,
    "agent": ModelTier.STRONG,
}


def route_request(task_type: str, *, explicit_model: str | None = None,
                  settings: ModelSettings | None = None) -> ModelSettings:
    """个人完整配置优先；环境选模仅允许配置过的 ID；缺失档位回退 ARK_MODEL。"""
    if settings is not None:
        if explicit_model and explicit_model != settings.model:
            raise ModelError("MODEL_NOT_AVAILABLE", "所选模型未配置，请重新选择模型。")
        return settings
    base = ModelSettings.from_env()
    models = {
        ModelTier.LITE: config.ARK_MODEL_LITE or base.model,
        ModelTier.DEFAULT: config.ARK_MODEL_DEFAULT or base.model,
        ModelTier.STRONG: config.ARK_MODEL_STRONG or base.model,
    }
    if explicit_model and explicit_model not in {base.model, *models.values()}:
        raise ModelError("MODEL_NOT_AVAILABLE", "所选模型未配置，请重新选择模型。")
    tier = TASK_MODEL_MAP.get(task_type, ModelTier.DEFAULT)
    selected = explicit_model or models[tier]
    log.info("Model route task=%s tier=%s model=%s explicit=%s", task_type, tier, selected, bool(explicit_model))
    return replace(base, model=selected)
