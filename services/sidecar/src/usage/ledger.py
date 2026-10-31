"""统一记录供应商已报告的用量；不保存请求正文或密钥。"""
from contextlib import contextmanager, closing
from contextvars import ContextVar
from datetime import datetime, timezone
from decimal import Decimal
from functools import wraps
import asyncio
import json
import logging
import sqlite3
from uuid import uuid4

from langchain_core.callbacks import AsyncCallbackHandler

from .. import config

context = ContextVar('usage_context', default=(None, 'other', None))
current_call = ContextVar('usage_call', default=None)


@contextmanager
def scope(owner=None, category=None, reference=None):
    previous = context.get()
    token = context.set((owner if owner is not None else previous[0], category or previous[1], reference or previous[2]))
    try:
        yield
    finally:
        context.reset(token)


def database(owner):
    """只打开当前已验证账号的本机用量数据库。"""
    if type(owner) is not int or owner <= 0:
        raise ValueError('用户身份无效。')
    root = config.DATA_ROOT / 'data/users' / str(owner)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    file = root / 'usage.sqlite3'
    if root.is_symlink() or file.is_symlink():
        raise ValueError('用量存储路径无效。')
    db = sqlite3.connect(file, timeout=10)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('''CREATE TABLE IF NOT EXISTS usage_events (
        id TEXT PRIMARY KEY, category TEXT NOT NULL, model TEXT NOT NULL,
        reference TEXT, created_at TEXT NOT NULL, payload TEXT NOT NULL)''')
    file.chmod(0o600)
    return db


def estimate(model, category, data, policy=None):
    """按记录时单价快照估算，后续改价不改写旧记录。"""
    if data.get('status') != 'reported':
        return None
    def price(value):
        number = Decimal(str(value))
        if not number.is_finite() or number < 0:
            raise ValueError('单价无效')
        return number
    try:
        from .settings import effective
        policy = policy or effective()
        rates = policy['model_prices'].get(model)
        if rates and 'input_tokens' in data and 'output_tokens' in data:
            cached = data.get('cached_input_tokens', 0)
            return str((price(rates['input']) * (data['input_tokens'] - cached) +
                        price(rates.get('cached_input', rates['input'])) * cached +
                        price(rates['output']) * data['output_tokens']) / 1000000)
        if rates and category == 'embedding' and 'total_tokens' in data:
            return str(price(rates['input']) * data['total_tokens'] / 1000000)
        if category == 'asr' and policy.get('asr_price_per_hour') is not None:
            return str(price(policy['asr_price_per_hour']) * price(data.get('audio_seconds', 0)) / 3600)
    except (ValueError, TypeError, KeyError, ArithmeticError, AttributeError):
        pass
    return None


def write(identifier, model, usage=None, *, status='reported', seconds=None, owner=None, category=None, reference=None):
    """同一次调用覆盖累计快照，防止流式事件和审批恢复重复累计。"""
    inherited = context.get()
    owner, category, reference = owner or inherited[0], category or inherited[1], reference or inherited[2]
    if not owner:
        return
    value = dict(usage or {})
    value.update(status=status)
    if seconds is not None:
        value['audio_seconds'] = seconds
    try:
        with closing(database(owner)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            if 'estimated_cost' not in value:
                from .settings import effective
                previous = db.execute('SELECT payload FROM usage_events WHERE id=?', (identifier,)).fetchone()
                policy = json.loads(previous[0]).get('pricing') if previous else None
                if policy is None:
                    selected = effective(owner)
                    # 每次调用固定使用开始记录时的价格，ASR 累计快照也不因中途改价重算。
                    policy = {'currency':selected['currency'],
                        'model_prices':{model:selected['model_prices'][model]} if model in selected['model_prices'] else {},
                        'asr_price_per_hour':selected.get('asr_price_per_hour')}
                value['pricing'] = policy
                value['currency'] = policy['currency']
                value['estimated_cost'] = estimate(model, category, value, policy)
            else:
                value.setdefault('currency', config.AGENT_COST_CURRENCY)
            db.execute('''INSERT INTO usage_events VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                payload=excluded.payload, model=CASE WHEN excluded.model='' THEN usage_events.model ELSE excluded.model END''', (identifier, category, model, reference,
                datetime.now(timezone.utc).isoformat(), json.dumps(value)))
    except (OSError, ValueError, sqlite3.DatabaseError):
        logging.getLogger(__name__).warning('Usage ledger write failed')


def raw_usage(body):
    """转换 OpenAI 风格用量；未报告时返回 None，不估算 Token。"""
    usage = body.get('usage') or {}
    total = usage.get('total_tokens')
    inp, out = usage.get('prompt_tokens', usage.get('input_tokens')), usage.get('completion_tokens', usage.get('output_tokens'))
    details = usage.get('prompt_tokens_details')
    cached = details.get('cached_tokens', 0) if isinstance(details, dict) else 0
    if type(inp) is int and inp >= 0 and type(out) is int and out >= 0:
        return {'input_tokens': inp, 'output_tokens': out, 'total_tokens': inp + out,
                'cached_input_tokens': min(inp, max(0, cached)) if type(cached) is int else 0}
    if type(total) is int and total >= 0:
        return {'total_tokens': total}
    return None


async def record_response(body, model):
    identifier = current_call.get()
    if identifier:
        value = raw_usage(body)
        await asyncio.to_thread(write, identifier, model, value, status='reported' if value is not None else 'unreported')


def tracked(function):
    """记录失败或取消但服务商未返回用量的调用。"""
    @wraps(function)
    async def wrapped(*args, **kwargs):
        identifier = str(uuid4())
        settings = args[1] if len(args) > 1 else kwargs['settings']
        token = current_call.set(identifier)
        await asyncio.to_thread(write, identifier, settings.model, status='unreported')
        try:
            return await function(*args, **kwargs)
        finally:
            current_call.reset(token)
    return wrapped


def summary(owner):
    """汇总各能力用量；有未知费用时仅展示已知部分。"""
    db = database(owner)
    try:
        rows = db.execute('SELECT category,model,payload FROM usage_events').fetchall()
    finally:
        db.close()
    result = {}
    for category, model, payload in rows:
        data = json.loads(payload)
        currency = data.get('currency', config.AGENT_COST_CURRENCY)
        row = result.setdefault((category, currency), {'category':category, 'calls':0, 'total_tokens':0, 'audio_seconds':0,
            'unreported_calls':0, 'unpriced_calls':0, 'estimated_cost':'0', 'currency':currency})
        row['calls'] += 1
        row['total_tokens'] += data.get('total_tokens', 0)
        row['audio_seconds'] += data.get('audio_seconds', 0)
        row['unreported_calls'] += data.get('status') != 'reported'
        cost = data.get('estimated_cost')
        if cost is None:
            row['unpriced_calls'] += 1
        else:
            row['estimated_cost'] = str(Decimal(row['estimated_cost']) + Decimal(cost))
    for row in result.values():
        if row['unpriced_calls'] == row['calls']:
            row['estimated_cost'] = None
    return {'items': list(result.values())}


class UsageCallback(AsyncCallbackHandler):
    def __init__(self):
        self.models = {}

    async def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        model = kwargs.get('invocation_params', {}).get('model', '')
        self.models[str(run_id)] = model
        await asyncio.to_thread(write, 'lc:' + str(run_id), model, status='unreported')

    async def on_llm_end(self, response, *, run_id, **kwargs):
        from ..harness.usage import reported_usage
        value = reported_usage(response)
        model = (response.llm_output or {}).get('model_name', '')
        if response.generations and response.generations[0]:
            model = getattr(response.generations[0][0], 'message', None)
            model = getattr(model, 'response_metadata', {}).get('model_name', '') or (response.llm_output or {}).get('model_name', '')
        model = model or self.models.get(str(run_id), '')
        await asyncio.to_thread(write, 'lc:' + str(run_id), model, value, status='reported' if value else 'unreported')
