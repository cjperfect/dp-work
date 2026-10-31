"""按运行记录供应商用量；预算只约束后续模型调用，不伪造账单。"""
import asyncio
import copy
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import tempfile

from langchain_core.callbacks import AsyncCallbackHandler

from .. import config
from ..providers.llm.schemas import ModelError


def usage_path(run_id):
    if not re.fullmatch(r'[a-fA-F0-9-]{36}', run_id):
        raise ModelError('USAGE_INVALID', '运行 ID 无效。')
    return config.WORKSPACE_DIR.parent / 'data' / 'agent-checkpoints' / (run_id + '.usage.json')


def read_usage(run_id):
    """待审批及中断运行从本机账本恢复已知消耗。"""
    path = usage_path(run_id)
    return json.loads(path.read_text()) if path.exists() else None


def write_usage(run_id, data):
    path = usage_path(run_id)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            os.chmod(temporary, 0o600)
            output.write(json.dumps(data, ensure_ascii=False).encode())
            output.flush()
            os.fsync(output.fileno())
            output.close()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def amount(value):
    """单价和费用预算只接受有限、非负数字。"""
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError('费用配置无效')
    return result


def reported_usage(response):
    """优先使用 LangChain 标准统计，兼容 OpenAI 格式；子项不重复相加。"""
    for generations in response.generations:
        if not generations:
            continue
        message = getattr(generations[0], 'message', None)
        usage = getattr(message, 'usage_metadata', None)
        if usage is not None:
            if all(type(usage.get(key)) is int and usage[key] >= 0 for key in ('input_tokens', 'output_tokens')):
                return {'input_tokens': usage['input_tokens'], 'output_tokens': usage['output_tokens'],
                        'total_tokens': max(usage.get('total_tokens', 0), usage['input_tokens'] + usage['output_tokens']),
                        'cached_input_tokens': min(usage['input_tokens'], usage.get('input_token_details', {}).get('cache_read', 0)),
                        'reasoning_tokens': min(usage['output_tokens'], usage.get('output_token_details', {}).get('reasoning', 0)),
                        'cached_input_reported': 'cache_read' in usage.get('input_token_details', {}),
                        'reasoning_reported': 'reasoning' in usage.get('output_token_details', {})}
    raw = (response.llm_output or {}).get('token_usage') or {}
    if all(type(raw.get(key)) is int and raw[key] >= 0 for key in ('prompt_tokens', 'completion_tokens')):
        return {'input_tokens': raw['prompt_tokens'], 'output_tokens': raw['completion_tokens'],
                'total_tokens': max(raw.get('total_tokens', 0), raw['prompt_tokens'] + raw['completion_tokens']),
                'cached_input_tokens': min(raw['prompt_tokens'], raw.get('prompt_tokens_details', {}).get('cached_tokens', 0)),
                'reasoning_tokens': min(raw['completion_tokens'], raw.get('completion_tokens_details', {}).get('reasoning_tokens', 0)),
                'cached_input_reported': 'cached_tokens' in raw.get('prompt_tokens_details', {}),
                'reasoning_reported': 'reasoning_tokens' in raw.get('completion_tokens_details', {})}
    return None


class UsageLedger(AsyncCallbackHandler):
    """所有嵌套模型调用共用一个账本，回调以调用 ID 去重。"""
    raise_error = True
    # 使用框架的异步 gather，预算异常也会等待其他回调完成，避免遗留未 await 协程。
    run_inline = False

    def __init__(self, run_id, model, owner=None):
        self.run_id, self.model = run_id, model
        self.lock = asyncio.Lock()
        self.version = 0
        try:
            from ..usage.settings import UsageSettings, effective
            from ..usage.ledger import context
            saved = read_usage(run_id)
            # 审批恢复沿用原任务的单价和预算，后续设置修改仅影响新任务。
            self.policy = saved.get('pricing') if saved else None
            self.policy = UsageSettings.model_validate(self.policy or effective(owner if owner is not None else context.get()[0])).model_dump(mode='json', exclude_none=True)
            self.prices = self.policy['model_prices']
            self.cost_limit = amount(self.policy['cost_limit'])
            self.token_limit = self.policy['token_limit']
            self.currency = self.policy['currency']
            self.calls = {call['id']: call for call in saved['calls']} if saved else {}
            for call in self.calls.values():
                if call['status'] == 'running':
                    call['status'] = 'unreported'
            if self.cost_limit and model not in self.prices:
                raise ValueError('费用预算需要先配置当前模型单价')
        except (ValueError, TypeError, KeyError, OSError, InvalidOperation) as cause:
            raise ModelError('USAGE_CONFIG_INVALID', '用量账本或预算配置无效；设置费用预算时需配置对应模型单价。') from cause

    def snapshot(self):
        calls = list(self.calls.values())
        totals = {key: sum(call.get(key, 0) for call in calls) for key in (
            'input_tokens', 'output_tokens', 'total_tokens', 'cached_input_tokens', 'reasoning_tokens')}
        known = [call for call in calls if call['status'] == 'reported']
        cost_known = bool(calls) and all(call['status'] == 'reported' and call.get('estimated_cost') is not None
                                             and call.get('currency') == self.currency for call in calls)
        cost = str(sum((Decimal(call['estimated_cost']) for call in calls), Decimal(0))) if cost_known else None
        return {'run_id': self.run_id, **totals, 'calls': copy.deepcopy(calls),
                'reported_calls': len(known), 'unreported_calls': sum(call['status'] == 'unreported' for call in calls),
                'in_flight_calls': sum(call['status'] == 'running' for call in calls),
                'complete': bool(calls) and len(known) == len(calls), 'estimated_cost': cost, 'currency': self.currency,
                'cached_input_reported': bool(known) and all(call.get('cached_input_reported') for call in known),
                'reasoning_reported': bool(known) and all(call.get('reasoning_reported') for call in known),
                'token_limit': self.token_limit or None, 'cost_limit': str(self.cost_limit) if self.cost_limit else None}

    async def save(self):
        from ..usage.ledger import write
        for call in self.calls.values():
            await asyncio.to_thread(write, 'lc:' + call['id'], call['model'], call,
                                    status=call['status'], category='agent', reference=self.run_id)
        self.version += 1
        task = asyncio.create_task(asyncio.to_thread(write_usage, self.run_id, {**self.snapshot(), 'pricing': self.policy}))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    def check_budget(self):
        usage = self.snapshot()
        if self.token_limit and usage['total_tokens'] >= self.token_limit:
            raise ModelError('AGENT_TOKEN_BUDGET', '本次任务已达到 Token 预算，已停止后续模型调用。')
        if self.cost_limit and usage['estimated_cost'] is not None and Decimal(usage['estimated_cost']) >= self.cost_limit:
            raise ModelError('AGENT_COST_BUDGET', '本次任务已达到费用预算，已停止后续模型调用。')
        if (self.token_limit or self.cost_limit) and usage['unreported_calls']:
            raise ModelError('AGENT_USAGE_UNAVAILABLE', '模型未返回完整用量，无法校验任务预算，已停止后续模型调用。')
        if self.cost_limit and usage['reported_calls'] and any(call.get('estimated_cost') is None or call.get('currency') != self.currency
                                                              for call in self.calls.values() if call['status'] == 'reported'):
            raise ModelError('AGENT_USAGE_UNAVAILABLE', '当前任务的费用无法完整估算，已停止后续模型调用。')

    async def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        async with self.lock:
            self.check_budget()
            invocation = kwargs.get('invocation_params') or {}
            model = invocation.get('model') or invocation.get('model_name') or self.model
            if self.cost_limit and model not in self.prices:
                raise ModelError('USAGE_CONFIG_INVALID', '当前模型没有配置单价，已阻止费用预算内的未计价调用。')
            key = str(run_id)
            if key not in self.calls:
                self.calls[key] = {'id': key, 'model': model, 'status': 'running', 'currency': self.currency}
                await self.save()

    async def on_llm_end(self, response, *, run_id, **kwargs):
        async with self.lock:
            call = self.calls.get(str(run_id))
            if not call or call['status'] != 'running':
                return
            usage = reported_usage(response)
            call['status'] = 'reported' if usage is not None else 'unreported'
            if usage is not None:
                call.update(usage)
                price = self.prices.get(call['model'])
                if price:
                    cached = usage['cached_input_tokens']
                    cost = ((usage['input_tokens'] - cached) * amount(price['input']) +
                            cached * amount(price.get('cached_input', price['input'])) + usage['output_tokens'] * amount(price['output'])) / 1_000_000
                    call['estimated_cost'] = str(cost)
            await self.save()

    async def on_llm_error(self, error, *, run_id, **kwargs):
        if kwargs.get('response') is not None:
            await self.on_llm_end(kwargs['response'], run_id=run_id)
            return
        async with self.lock:
            call = self.calls.get(str(run_id))
            if call and call['status'] == 'running':
                call['status'] = 'unreported'
                await self.save()
