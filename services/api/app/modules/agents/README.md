# Agent API

- GET `/api/agents/models`：查询 Sidecar 实际配置的模型，登录后可用，不返回密钥。
- POST `/api/agents/chat`：登录校验、输入校验、SSE 转发及断开清理。
- 模型执行和工具循环由 Sidecar 的 `src/agents/agent.py`（LangChain create_agent / LangGraph）实现。
- 当前会话历史由前端本地保存，暂不创建 PostgreSQL 会话或消息表。
