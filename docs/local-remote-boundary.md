# 本地与远程边界

## 远程业务

- 用户登录、注册与账号权限验证。
- 会议数据、原始转写、纪要、版本、协同、归档和生成任务。
- 知识库、原文件、解析结果、分块/向量、ES 索引、检索及异步处理任务。

PG 保留这些业务表以及设备任务通道基础设施。设备连接、心跳和任务回执仅用于会议/知识库任务，并不代表会话仍远程保存。

## 本地业务

- Agent 聊天、历史和分支、标题、草稿、排队、引导、停止、运行和审批。
- 项目名称、目录、设备关联及原生目录授权。
- 个人模型/ASR 参数、加密 API Key 和测试连接。
- AGENT.md、工作目录、技能市场查询及本机安装/卸载。
- 飞书 CLI、授权流程、二维码、验证状态和凭证。
- 外观和桌面偏好。

界面 API 文件沿用原有模块与请求地址，但本地前缀 `/api/agents|settings|skills|connectors` 在 Axios 适配器中进入 Preload IPC，不发送 HTTP，也不在失败时回退云端。Main 校验主窗口/主框架来源、白名单业务路径及已验证用户，注入 owner/device，再调用 Sidecar 的语义 JSON-RPC。JSON 和 SSE 都支持流式传递与取消。旧云端业务路由和 Python 包装代码已移除。

登录首次需要远程验证。Main 缓存已验证凭证的 SHA-256 摘要及本机用户/设备标识，不能通过修改 Renderer 的 user ID 读取其他账号数据。相同已验证登录支持离线重启；注销时清理摘要并取消在途调用，账号切换停止旧流。

## 跨边界调用

Agent 关联知识库时，Main 仅向远程知识库能力接口提交知识库 ID，获取有时效和范围限制的 token。聊天历史不随该请求上传。检索 Tool 使用范围 token 查询远程知识库，最终模型请求由本机直连模型提供商。

会议的 `POST /api/meetings/{id}/asr/session` 验证会议归属后，经用户设备申请一次性 ASR 票据；个人密钥由本机读取，转写仍连接本机 Sidecar WebSocket。纪要、解析和向量化的云端异步任务保留设备通道，由本机 Sidecar 执行并将业务结果交回对应远程模块。

设备 RPC 白名单仅包含 meetings.minutes.generate、knowledge.parse、knowledge.chunks、knowledge.embed、asr.sessions。云端与 Main 双方限制，不能借设备通道远程查询会话、读取设置、安装技能或触发 CLI 授权。

“本地”指本项目的执行与持久化位置，不意味着所有功能都不访问网络：模型、飞书和 skills.sh/GitHub 由本机直接访问各自提供商。纯浏览器缺少原生桥接时，本地功能明确失败，不连接已移除的云端接口。

## 本地文件

- sessions/<user-id>/*.jsonl：会话追加事件。
- data/users/<user-id>/state.sqlite3：会话投影、项目、消息分支、运行和审批。
- data/projects.json：Electron 原生文件夹选择器的目录授权。
- data/agent-checkpoints/*.sqlite3：LangGraph 执行检查点。
- config/users/<user-id>/services.json + services.key：加密个人配置。
- connectors/feishu/<user-id>/：CLI 授权凭证。
- workspace/<agent-code>/：默认工作目录、AGENT.md、技能。
- memories/<user-id>/：长期记忆独立空间，自动提取暂未开启。

根目录开发环境为仓库 `.dp-work`，安装版为用户主目录 `~/.dp-work`。旧 PG 数据已有受权限保护的备份，迁移 0022/0023/0024 删除了旧会话、消息、运行、审批、个人设置及项目表。
