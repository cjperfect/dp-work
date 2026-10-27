# Agent 运行时

Agent 专属逻辑集中在 `agent.py`：

- 输入消息校验、通用 / 产品 Agent 提示词。
- 从环境读取方舟模型配置，通过 LangChain 创建模型。
- 使用 `create_deep_agent` 管理模型与工具循环，所有 Agent 默认拥有 ls、read_file、write_file、edit_file、glob、grep、execute；关联知识库时再追加检索工具。
- 流式事件转换、超时、执行步数限制、取消清理和安全错误。

模型共享配置保留在 `providers/llm/schemas.py`，会议纪要也使用它。业务入口统一由 `transport/handlers.py` 处理 JSON-RPC 方法。

配置读取 `.env`：ARK_API_KEY、ARK_MODEL、ARK_BASE_URL、ARK_TIMEOUT_SECONDS、ARK_MAX_TOKENS、AGENT_MAX_STEPS。

调用链：前端 → API → Electron 设备通道 → Sidecar `agents.chat` JSON-RPC。Sidecar 按方法名直接分发，返回 start、delta、done、error 事件。

会话历史和消息分支由 API 保存到 PostgreSQL；API 从当前选中路径构造普通消息发送给 Sidecar，不启用共享内存 checkpointer。企业技能、连接器与审批后续接入。

关联知识库时，由 `knowledge/rag/tool.py` 提供 `search_knowledge` Tool；只有 API 验证知识库归属后签发的短时范围授权可以检索，模型不接收用户登录令牌或自选知识库范围。

标题由 `agent.py` 的 `generate_title` 调用 LLM 生成，内部接口 `/internal/agents/title`；独立限制 30 秒和 256 输出 token，结果限制为单行 30 字以内。前端通过 assistant-ui 的 generateTitle 适配器触发，去重请求、保护手动重命名，并缓存到当前设备。

默认工具实现在 [tools](../tools/README.md)，绑定当前 Agent 的独立 workspace；execute 支持超时、输出限制和取消。默认工具始终提供，知识库工具按本次授权追加。

已安装技能通过 `skills=["/skills/"]` 交给 Deep Agents 按需加载，目录位于各 Agent 的 workspace/skills。搜索、安装和卸载见 [skills](../skills/README.md)，页面及聊天侧栏展示本机真实安装结果。

各 Agent 的系统提示词保存在 `.dp-work/workspace/<agent_code>/AGENT.md`，每次运行重新读取，修改后下次对话生效。首次使用从 `templates/<agent_code>/AGENT.md` 初始化，已有文件不覆盖。模板随 Sidecar 安装包分发，Python 不内置业务提示词。空文件、非法编码、超大文件会返回配置错误。运行时只追加 Agent 标识与实际工具列表，技能仍由 Deep Agents 按需加载。

聊天侧栏配置弹窗支持编辑提示词，经鉴权 API、设备通道调用 `agents.config.update` 保存本机 AGENT.md。保存使用旧内容校验和原子替换，冲突返回 409；生效范围为下次运行，不改变正在执行的会话。
