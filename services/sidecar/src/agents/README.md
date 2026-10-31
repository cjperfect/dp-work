# Agent 运行时

Agent 专属逻辑集中在 `agent.py`：

- 输入消息校验、通用 / 产品 Agent 提示词。
- 从环境读取方舟模型配置，通过 LangChain 创建模型。
- 使用 `create_deep_agent` 管理模型与工具循环，所有 Agent 默认拥有 ls、read_file、write_file、edit_file、glob、grep、execute；关联知识库时再追加检索工具。
- 流式事件转换、超时、执行步数限制、取消清理和安全错误。

模型共享配置保留在 `providers/llm/schemas.py`，会议纪要也使用它。业务入口统一由 `transport/handlers.py` 处理 JSON-RPC 方法。

配置读取 `.env`：ARK_API_KEY、ARK_MODEL、ARK_BASE_URL、ARK_TIMEOUT_SECONDS、ARK_MAX_TOKENS、AGENT_MAX_STEPS。

调用链：前端 → Electron 本地 IPC → Sidecar `agents.chat` JSON-RPC。Sidecar 按方法名直接分发，返回 start、delta、approval、done、error 事件。

会话历史、消息分支和运行审批由本机 sessions 模块保存至 JSONL 与 SQLite；Sidecar 从当前路径构造模型上下文，执行恢复使用独立 LangGraph SQLite checkpoint。技能已按需加载，连接器工具后续接入。

关联知识库时，由 `knowledge/rag/tool.py` 提供 `search_knowledge` Tool；只有 API 验证知识库归属后签发的短时范围授权可以检索，模型不接收用户登录令牌或自选知识库范围。

标题仅根据用户第一条消息，由 `agent.py` 的 `generate_title` 调用 LLM 生成，RPC 方法 `agents.title`；独立限制 30 秒和 256 输出 token，结果限制为单行 30 字以内。前端通过 assistant-ui 的 generateTitle 适配器触发，去重请求、保护手动重命名，并保存到本机会话。

默认工具实现在 [tools](../tools/README.md)，绑定当前 Agent 的独立 workspace；execute 支持超时、输出限制和取消。默认工具始终提供，知识库工具按本次授权追加。

已安装技能通过 `skills=["/skills/"]` 交给 Deep Agents 按需加载，目录位于各 Agent 的 workspace/skills。搜索、安装和卸载见 [skills](../skills/README.md)，页面及聊天侧栏展示本机真实安装结果。

各 Agent 的系统提示词保存在 `.dp-work/workspace/<agent_code>/AGENT.md`，每次运行重新读取，修改后下次对话生效。首次使用从共享子包 `packages/agent-templates/templates/<agent_code>/AGENT.md` 初始化，已有文件不覆盖。模板随 Sidecar 安装包分发，Python 不内置业务提示词。空文件、非法编码、超大文件会返回配置错误。运行时只追加 Agent 标识与实际工具列表，技能仍由 Deep Agents 按需加载。

聊天侧栏配置弹窗支持编辑提示词，经 Electron 本地 IPC 调用 `agents.config.update` 保存本机 AGENT.md。保存使用旧内容校验和原子替换，冲突返回 409；生效范围为下次运行，不改变正在执行的会话。

人工审批：通过 HumanInTheLoopMiddleware 的 `when` 按参数判定风险，子 Agent 使用同一策略。普通文档创建与编辑、简单查看命令直接执行；`.env`、Git 配置、凭证、Agent 提示词和技能的修改，以及删除、重定向、复杂 Shell 或无法分类的命令需要审批。规则位于 `harness/tool_policy.py`。只支持允许原操作一次或拒绝，不允许客户端替换工具参数。待审批记录保存在本机 SQLite；执行快照位于 `.dp-work/data/agent-checkpoints/<run_id>.sqlite3`，正常完成后清理。刷新页面可以恢复待审批卡片，运行恢复到原设备，原工具结果与当前回复保持连续。等待最长 24 小时，过期、取消、已决定的审批不能重新执行。设备离线或检查点缺失时失败并保留审批回执，不自动重放副作用。

图片输入：复用 assistant-ui 的 SimpleImageAttachmentAdapter 和附件组件，支持粘贴、预览及移除 PNG/JPEG/WebP（每条最多 3 张，每张最多 1 MB）。图片经 Electron 本机 RPC 写入 `.dp-work/data/users/<owner>/attachments/<sha256>`，消息和排队记录仅保存引用。执行时由 Sidecar 读取并构造 HumanMessage 的 image_url 内容，实际图片会发送给配置的模型服务，须选择支持视觉输入的模型。图片历史通过本机接口恢复预览；不存在的附件不阻止文字历史展示。当前图片消息可排队，暂不支持 Steering。

思考展示：providers/llm/chat.py 保留模型公开返回的 reasoning_content 及标准 reasoning 文本/摘要。供应商加密字段仅在当前工具循环中原样回传，不解密、不展示。reasoning / reasoning_end 与正文 delta 分开发送，由 sessions 按秒保存为本机消息 context.reasoning，并用 execution_order 保留思考和工具调用的发生顺序。前端复用 assistant-ui Reasoning、ToolGroup、ToolFallback，可展开思考文本、工具参数和结果；没有返回思考的模型不生成虚构思考面板。默认不强制开启供应商 thinking 参数。

对话压缩：沿用 Deep Agents 的自动摘要阈值与历史保存策略；CompactionMiddleware 在实际生成摘要时发送 compaction 状态事件。前端在当前会话输入框上方显示“正在优化对话，请稍候，可能需要几分钟”，完成、失败或停止后收起。摘要内容不混入聊天正文。
