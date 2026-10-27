# Agent API 与会话历史

- `GET /api/agents/models`：查询可用模型，不返回密钥。
- `POST /api/agents/title`：调用当前用户模型生成标题；前端再保存标题，人工重命名优先。
- `POST /api/agents/threads/{id}/chat`：使用 PG 当前消息路径执行 Agent，保存流式回答及完成/失败/取消状态。
- `POST /api/agents/chat`：旧临时执行接口，已标记 deprecated，不保存历史；正式聊天界面不再调用。
- 模型和工具循环由 Sidecar 的 `src/agents/agent.py`（create_agent / LangGraph）执行，API 负责业务存储与权限。

## 会话接口

| 方法   | 路径                                | 功能                                                         |
| ------ | ----------------------------------- | ------------------------------------------------------------ |
| GET    | `/api/agents/threads`               | 全部 Agent 会话元数据；可按 `q` 搜索标题、按 `agent_id` 筛选 |
| POST   | `/api/agents/threads`               | 根据请求 ID 幂等创建                                         |
| GET    | `/api/agents/threads/{id}`          | 当前消息路径、全部分支和草稿                                 |
| PATCH  | `/api/agents/threads/{id}`          | 重命名，区分人工/自动生成标题                                |
| PATCH  | `/api/agents/threads/{id}/draft`    | 按版本保存草稿和上下文选择                                   |
| PUT    | `/api/agents/threads/{id}/messages` | 按版本保存消息节点和当前路径                                 |
| DELETE | `/api/agents/threads/{id}`          | 删除消息和正文，保留 ID 墓碑防止旧页面/旧迁移复活            |
| POST   | `/api/agents/threads/import`        | 一次迁移设备历史，PG 已有记录优先                            |

所有接口要求登录，只能操作本人会话。成功 HTTP 200，响应沿用 `{code, message, data}`；SSE 为事件流。Swagger 在 `/api/docs`。

## 数据与恢复

- `conversations`：用户、Agent 归属（1=general / 2=product）、标题、草稿、知识库选择、当前消息路径、版本和执行租约。
- `conversation_messages`：复合主键 `(conversation_id, id)`；父 ID 保存编辑分支，正文、状态、上下文快照为独立字段。
- 列表只查元数据，不返回历史正文或草稿；打开会话才加载消息。草稿保存不上传整段历史。
- 草稿和路径写入要求 `expected_revision`，过期返回 409，缺失/越权返回 404；不会用 PUT 自动重建已删除会话。
- 用户问题与 assistant 占位节点先保存，再开启 SSE；模型上下文从 PG 当前路径构造，忽略客户端伪造的历史和 Agent 代码。
- API 按秒保存流式增量，`done` 在最终结果事务提交后发出。断开保存已收到的部分；异常退出后读取时恢复过期租约为失败。
- 前端会话正文不再写 localStorage。原设备历史逐会话幂等迁入 PG，全部成功后清理旧副本；失败保留源数据并提示重试。
- 本地仍缓存 Agent 配置和当前选中会话 ID。Agent 配置暂未迁移数据库，本次范围为会话与消息。

执行迁移：仓库根目录 `pnpm migrate`。迁移版本 `0017_conversations`。
