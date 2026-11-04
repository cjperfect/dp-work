"""用量及预算管理适配。"""
import asyncio
from ..types import LocalSettingsInput, OperationError


async def usage_summary(params, state):
    from ...usage.ledger import summary
    owner = params.get('owner_id')
    if type(owner) is not int or owner <= 0:
        raise OperationError(400, '用户身份无效。')
    return await asyncio.to_thread(summary, owner)


async def usage_settings(action, params, state):
    """读写已验证账号的本机单价和任务预算。"""
    from ...usage import settings
    body = LocalSettingsInput.model_validate(params)
    try:
        if action == 'read':
            return await asyncio.to_thread(settings.read, body.owner_id)
        return await asyncio.to_thread(settings.save, body.owner_id, body.body)
    except ValueError as cause:
        raise OperationError(400, str(cause)) from cause

