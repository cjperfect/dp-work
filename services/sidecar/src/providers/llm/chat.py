"""保留兼容模型服务明确返回的思考字段，不推断或生成思考文本。"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, AIMessageChunk


class ReasoningChatOpenAI(ChatOpenAI):
    def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
        result = super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)
        choices = chunk.get('choices') or chunk.get('chunk', {}).get('choices') or []
        delta = choices[0].get('delta', {}) if choices else {}
        if result is not None and isinstance(result.message, AIMessageChunk):
            for field in ('reasoning_content', 'encrypted_content'):
                if isinstance(delta.get(field), str): result.message.additional_kwargs[field] = delta[field]
        return result

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        # 保留当前工具循环所需的供应商字段；加密块仅回传，不向界面展示。
        for message, output in zip(self._convert_input(input_).to_messages(), payload.get('messages', [])):
            if isinstance(message, AIMessage):
                for field in ('reasoning_content', 'encrypted_content'):
                    if isinstance(message.additional_kwargs.get(field), str): output[field] = message.additional_kwargs[field]
        return payload


def reasoning_text(message):
    """只提取服务公开返回的文本，忽略加密字段和其他内部元数据。"""
    value = message.additional_kwargs.get('reasoning_content')
    if isinstance(value, str):
        return value
    blocks = message.content if isinstance(message.content, list) else []
    texts = []
    for block in blocks:
        if not isinstance(block, dict) or block.get('type') != 'reasoning':
            continue
        text = block.get('reasoning', block.get('text'))
        if isinstance(text, str): texts.append(text)
        for summary in block.get('summary', []):
            if isinstance(summary, dict) and isinstance(summary.get('text'), str): texts.append(summary['text'])
    return ''.join(texts)
