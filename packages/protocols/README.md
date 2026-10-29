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

`agents.steer` 投递运行中引导，参数为 `run_id`、`owner_id`、`thread_id`、`id`、`content`。只在原运行活跃且账号/会话匹配时接收，下一轮模型调用前消费；接收成功不代表已经生效，业务 `steering` SSE 事件才表示已消费。该短调用允许在业务执行槽已满时接收，不取消原请求；`$/cancelRequest` 仍仅表示停止。

本机会话使用 `sessions.*` 方法：list/get/create/draft/messages/rename/delete/import/project/chat/steer、approvals/approval.lookup/approval.decide、runs.list/runs.get/runs.cancel。身份由 API 注入 `owner_id`，会话 ID 为 `thread_id`，操作输入放在 `body`；运行和恢复额外携带仅用于执行的 runtime/retrieval_token，不持久化这些凭证。`sessions.chat` 与 `sessions.approval.decide` 返回同样的流式事件，终态在本机 JSONL 和 SQLite 提交后发出。project.detach 解除本机会话的项目关联。

个人服务设置通过 settings.read/save/test-local/configured 管理，传入已认证 owner_id、kind 与表单 body。读取不返回明文 API Key；已保存的密钥只由 Sidecar 在本机解密。agents.models/title 和 meetings.minutes.generate 使用 owner_id，agents.chat 使用 workspace_owner_id，asr.sessions 使用 owner_id 来选择当前设备个人配置。API 不再从 PG 取 runtime 或已保存密钥。

本机项目使用 projects.list/create/get/rename/delete，参数为 owner_id/device_id/body。设备和用户由 API 认证后注入，原生目录授权由本机校验；名称、路径、设备关联保存本机 projects 表，云端不再有 agent_projects 表。

本地/远程边界：只有登录注册、会议、知识库调用云端业务 API。agents/sessions/projects/settings/skills/connectors 由 Renderer → Preload → Main 本地网关 → stdio RPC 直达 Sidecar。云端不再提供这些业务路由，设备任务白名单限 meetings.minutes.generate、knowledge.parse/chunks/embed、asr.sessions。知识库检索范围授权属于远程知识库接口，不传递聊天历史。DesktopBridge 新增 localRequest/onLocalChunk/cancelLocalRequest，用于有界的本地 JSON/SSE 请求，来源检查与账号注入均在 Main。

## 本机文件恢复

`sessions.files.undo` 接收 Main 注入的 `owner_id`、`thread_id` 及 `body.change_id`，返回 `{change, thread}`。Sidecar 校验会话归属、运行状态与磁盘快照，恢复成功后返回最新会话 revision。Renderer 不提供任意恢复路径或文件内容；此方法不进入云端设备任务白名单。
