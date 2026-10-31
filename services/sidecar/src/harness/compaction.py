"""保留 Deep Agents 压缩策略，并向界面报告摘要生成状态。"""
import asyncio
from uuid import uuid4

from deepagents.middleware.summarization import (
    SummarizationMiddleware,
    compute_summarization_defaults,
)
from langgraph.config import get_stream_writer


class CompactionMiddleware(SummarizationMiddleware):
    @property
    def name(self):
        """替换框架默认压缩中间件，避免重复压缩。"""
        return "SummarizationMiddleware"

    async def _acreate_summary(self, messages_to_summarize):
        """在实际生成摘要期间发送状态，异常和取消仍交由框架处理。"""
        # 适配固定版本 deepagents==0.7.32 的摘要入口，不改动其提示词和保留策略。
        writer = get_stream_writer()
        event_id = str(uuid4())
        writer({'type': 'compaction', 'id': event_id, 'status': 'running'})
        status = 'failed'
        try:
            summary = await super()._acreate_summary(messages_to_summarize)
            status = 'complete'
            return summary
        except asyncio.CancelledError:
            status = 'cancelled'
            raise
        finally:
            writer({'type': 'compaction', 'id': event_id, 'status': status})


def compaction_middleware(model, backend):
    """沿用模型对应的默认阈值、保留窗口和历史落盘逻辑。"""
    defaults = compute_summarization_defaults(model)
    return CompactionMiddleware(model=model, backend=backend,
        trigger=defaults['trigger'], keep=defaults['keep'],
        truncate_args_settings=defaults['truncate_args_settings'],
        trim_tokens_to_summarize=None)
