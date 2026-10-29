"""将现有 API 服务调用转换为设备的语义 RPC 输入。"""
import base64
import json
from urllib.parse import parse_qs

ROUTES = {
    ("POST", "/internal/meetings/minutes/generate"): "meetings.minutes.generate",
    ("POST", "/internal/knowledge/parse"): "knowledge.parse",
    ("POST", "/internal/knowledge/chunks"): "knowledge.chunks",
    ("POST", "/internal/knowledge/embed"): "knowledge.embed",
    ("POST", "/internal/asr/sessions"): "asr.sessions",
}


def rpc_input(verb, path, query, content):
    """HTTP 兼容映射仅留在 API，设备和 Sidecar 只接收方法名及业务参数。"""
    method = ROUTES.get((verb, path))
    if not method:
        raise ValueError("不支持的执行方法。")
    if method == "knowledge.parse":
        values = parse_qs(query)
        params = {"file_type": values.get("file_type", ["pdf"])[0],
                  "content_base64": base64.b64encode(content).decode()}
    else:
        params = json.loads(content) if content else {}
        if not isinstance(params, dict):
            raise ValueError("业务参数必须为对象。")
    return {"method": method, "params": params}
