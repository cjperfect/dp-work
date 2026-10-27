# 用户本机执行通道

目标部署：Web / Electron / Sidecar 在用户本机，API / PostgreSQL / ES / RabbitMQ / Worker 在云端。

```text
Web --HTTPS--> 云端 API --PG 执行消息--> Electron Main 主动建立的 WSS
                                         ↓
                                stdin/stdout JSON-RPC → 本机 Sidecar
                                         ↓
                              模型服务 / 云端 RAG 检索回调
```

API 设置 `SIDECAR_TRANSPORT=device` 后，所有聊天、标题、模型列表、个人服务测试、ASR 票据、解析、分块、向量化都通过设备通道执行，不再请求云服务器上的 localhost Sidecar。`http` 仅用于集中式开发兼容。设备连接入口为 `/api/devices/connect`，登录 JWT 放在首帧，不放 URL。Electron 为当前登录建立连接，退出登录立即断开并取消本机任务。

- 设备标识由用户 ID 与本机安装 ID 派生。同一台电脑切换账号不会复用其他用户的设备记录。
- Web 通过受限 IPC 将登录状态交给 Main，请求携带 `X-Device-ID`。API 验证设备归属；未指定设备时仅在本人恰好有一个在线设备时自动选择。
- API 将内部兼容调用映射为 `packages/protocols` 定义的方法名与业务参数，Main 只执行方法白名单，不接受云端提交任意 URL、端口、命令或请求头。本机 stdio RPC 不需要内部 HTTP 服务密钥，凭证只用于独立 HTTP 兼容模式。
- 文件输入通过有登录和设备校验的 HTTPS 请求获取，不把 20 MB 文件塞进 WebSocket 单帧。临时输入在 PG 内加密，执行收到响应头或结束后清理。
- RPC 元数据和响应分片由 PG 暂存并使用 NOTIFY 唤醒，因此 API 多实例与独立 MQ Worker 可共用设备连接，不依赖单个 API 进程内存。
- 同一设备最多四个在途调用。分片限制大小、顺序与总量；终态和设备会话号防止迟到回复写回新连接。取消会通知 Main 发送 RPC 取消通知，中止本机执行任务。
- 后台任务的 `task_outbox.device_id` 保存发起设备。离线时不领取业务任务，保留消息并延期；执行中断后沿用版本/租约恢复，不盲目重放外部副作用。
- SSE 和输入只发给目标设备。短连接断开不重新分配给其他设备；任务是否重试由业务层决定。已结束 RPC 临时记录保留最多约一小时，业务结果仍由原业务表保存。

## 云端部署

执行 `pnpm migrate`，设置 API `.env` 中 `SIDECAR_TRANSPORT=device`，API 与 Worker 使用同一 PG、JWT 密钥和共享的上传文件目录。启动 API 和 MQ Worker；云端不启动 Python Sidecar。网关为 `/api/devices/connect` 开启 WebSocket Upgrade，允许长连接，并保留现有业务 SSE / WebSocket 转发。`CORS_ORIGINS` 需包含桌面 Web 固定来源 `http://127.0.0.1:34731`，自定义端口时同步调整。

桌面构建时指定 `DESKTOP_API_BASE_URL=https://你的API域名`；生产只接受 HTTPS，设备连接自动使用 WSS。安装版内置 Sidecar，不需要开放用户电脑入站端口。公网模型 Key 可以通过个人设置保存，或配置在用户自己的 `~/.dp-work/config/sidecar.env`；不要将服务端 `.env` 放入安装包。

RAG 回调使用 API 签发的 240 秒范围授权，在 device 模式下不再要求所有客户端共用一个 `X-Internal-Token`。用户、知识库和账号状态仍由 API 验证。

## 验证

`tests/integration/test_device_bridge_db.py` 使用独立测试库、真实 API 进程和 Node Main 桥接替身，验证流式对话、取消、Worker 解析、离线延期和重连。生产模型与 ASR 不在测试中调用。
