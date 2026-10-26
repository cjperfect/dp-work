# Agent 运行时

Agent 专属逻辑集中在 `agent.py`：

- 输入消息校验、通用 / 产品 Agent 提示词。
- 从环境读取方舟模型配置，通过 LangChain 创建模型。
- 使用 `create_agent` 管理模型与工具循环，目前业务工具为空。
- 流式事件转换、超时、执行步数限制、取消清理和安全错误。

模型共享配置保留在 `providers/llm/schemas.py`，会议纪要也使用它。HTTP 内部接口保留在 `transport/internal.py`。

配置读取 `.env`：ARK_API_KEY、ARK_MODEL、ARK_BASE_URL、ARK_TIMEOUT_SECONDS、ARK_MAX_TOKENS、AGENT_MAX_STEPS。

调用链：前端 → API `/api/agents/chat` → Sidecar `/internal/agents/chat`。API 校验登录，内部调用验证 X-Internal-Token，SSE 返回 start、delta、done、error。

会话历史暂由客户端本地保存，不启用共享内存 checkpointer 或 PG 会话表。RAG、企业技能、连接器与审批后续接入。

关联知识库时，由 `knowledge/rag/tool.py` 提供 `search_knowledge` Tool；只有 API 验证知识库归属后签发的短时范围授权可以检索，模型不接收用户登录令牌或自选知识库范围。
