# Agent 已迁至本地

云端不再注册 Agent、会话、项目、运行和审批业务接口。前端仍使用原来的业务 API 模块，但 Axios 按模块选择本地 IPC 适配器，不发送 HTTP 请求。

`apps/web/src/lib/local-transport.ts` → Electron Preload → `apps/desktop/src/main/local/gateway.ts` → Sidecar stdio JSON-RPC → `services/sidecar/src/sessions/`。

会话 JSONL、SQLite 索引、项目、提示词、技能、运行、审批和 LangGraph checkpoint 均在 `.dp-work`。用户身份在云端登录验证后，本机缓存凭证摘要；已验证的相同凭证支持离线恢复本地功能。退出或账号切换会取消当前本地调用。

关联远程知识库时，Main 仅向 `/api/knowledge-bases/retrieval-capability` 提交知识库 ID，取得限定范围的短期授权，不上传聊天历史。实际检索仍属于远程知识库功能。

PG 迁移 0022/0024 已移除旧会话、消息、运行、审批及项目表，旧数据备份保留在 `.dp-work/backups`。
