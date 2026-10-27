# Sidecar JSON-RPC 协议

统一管理 Web、Electron Main 与 Python Sidecar 之间的通信协议。

- `protocol.json`：跨语言唯一配置源，包含方法名和说明、控制通知、错误码与容量限制。
- `src/rpc.ts`：JSON-RPC 消息类型与方法名校验函数，从 `@dp-work/protocols/rpc` 导入。
- `src/desktop.ts`：Preload 暴露的桌面 IPC 类型，从 `@dp-work/protocols/desktop` 导入。
- `src/asr.ts`：ASR WebSocket 消息类型，从 `@dp-work/protocols/asr` 导入。
- `src/index.ts`：统一导出入口。
- Python 通过 `services/sidecar/src/transport/protocol.py` 直接读取同一个 JSON；PyInstaller 将它放进 `protocols/protocol.json`，Python 不执行 TS 文件。

修改方法或限制时先更新 `protocol.json`，涉及消息字段时同步更新 TS 类型与 Python 的运行时校验，并运行双方测试。重新构建桌面安装包才会更新内置 Python 协议副本。

## 通信约定

UTF-8 JSONL，每行一个 JSON-RPC 2.0 对象；ID 为字符串。stdout 仅输出协议，日志写 stderr。单个 Sidecar 最多四个业务调用并发，健康检查独立响应。

请求使用语义方法名，例如 `knowledge.parse`、`agents.chat`。`params` 直接包含业务参数，例如聊天的 `thread_id`、`messages`，解析的 `file_type`、`content_base64`。Sidecar 的 `transport/handlers.py` 按方法名找到处理函数并校验业务参数，不经过 HTTP / ASGI 路由。现有 API 调用的路径适配只保留在 API 端 `infrastructure/sidecar/requests.py`。

```json
{
  "jsonrpc": "2.0",
  "id": "task-1",
  "method": "agents.models",
  "params": {}
}
```

业务调用先发 `stream.head`（状态及内容类型），再发零个或多个 `stream.chunk`（ID、连续 seq 和 Base64 数据），最后返回 `result: {"complete":true}`。聊天内容仍是原有 SSE 事件字节，Main 通过同一云端连接转发给 API。`system.health` 直接返回服务及实例状态。

取消是无 ID 的 `$/cancelRequest` 通知，`params.id` 指定目标请求；接收端取消对应异步任务。调用超时、进程退出及管道断开都会中断在途请求；重启后不重放旧请求，业务重试由 API 的任务机制决定。

ASR 音频保持独立 WebSocket，ASR 连接票据通过 `asr.sessions` RPC 创建，二者共用同一进程中的会话状态。桌面 stdio 模式不开放网络 `/internal` 接口；独立 HTTP 模式仍用于集中式开发兼容。
