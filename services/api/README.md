# API

FastAPI + SQLAlchemy 2.x + Alembic + asyncpg，业务数据统一保存在 PostgreSQL。API、Sidecar 部署在服务器，Electron/Web 负责客户端界面和音频采集。

## 启动

配置 `services/api/.env`，在仓库根目录执行：

```bash
pnpm db:up
pnpm migrate
pnpm dev:api
```

数据库开发默认账号、密码均为 `chenjiang`，库名 `dp_work`。Docker 数据卷持久化，`pnpm db:down` 仅停止服务并保留数据卷。数据库迁移和 SQLite 历史数据导入见 [migrations/README.md](migrations/README.md)。

## 接口约定

- Swagger：`http://localhost:8000/api/docs`，OpenAPI：`/api/openapi.json`。
- 无 `/v1` 前缀，成功统一 HTTP 200，JSON 格式 `{code,message,data}`。
- 登录、注册使用公钥接口返回的 RSA 公钥加密密码；JWT 有效期一周。
- Swagger 的 Authorize 填写登录返回的 token；受保护接口按用户隔离资源，无权访问统一返回 404。
- 分页返回 `item`、`page`、`page_size`、`total`。

## 业务模块

| 模块         | 已有接口                                                                        |
| ------------ | ------------------------------------------------------------------------------- |
| auth / users | 登录、注册、密码传输公钥、角色和状态映射                                        |
| knowledge    | 知识库 CRUD 和分页搜索；文档读取、自动保存、删除；Markdown/PDF 上传、源文件下载 |
| meetings     | 创建、列表、详情、按版本保存、删除、旧浏览器记录导入                            |
| connectors   | 飞书 CLI 配置、用户授权、验证和退出                                             |

在线文档和会议纪要保留富文本块 JSON；源文件放文件存储目录，数据库保存元数据。会议保存同时提交状态、确认转写和纪要，版本冲突返回 409，删除会议级联删除确认转写和纪要。AI 生成纪要已接入方舟调用链路，需配置模型凭证；生成后的会议纪要已接入跨用户实时协作、分享和版本历史；原始转写仅由创建者纠错。

## 分层

`router.py` 处理请求与认证，`service.py` 负责业务和事务，`repository.py` 负责 SQLAlchemy 数据访问，`models.py` 定义表，`schemas.py` 定义校验和响应结构。函数仅保留简短用途注释。

`updated_at` 由应用层维护。API 启动只初始化连接池并创建缺省管理员（已有账号不重置），DDL 通过 Alembic 显式执行。

## 真实会议纪要生成

- `POST /api/meetings/{id}/minutes/generate`，提交 `{expected_revision}`，成功返回 HTTP 200 以及 `task_id`、`source_revision` 和最新会议状态。
- 仅会议创建者可提交；会议必须结束且有原始内容。API 锁定会议并将最新转写快照保存在 `meeting_generation_jobs`。正在执行时重复提交复用同一任务；生成期间拒绝修改原始内容。
- 执行器从 PostgreSQL 领取任务，通过内部凭证调用 Sidecar。模型调用期间不持有数据库事务。成功时原子保存 Markdown、模型和提示词版本，并更新状态为 `ready`；失败保留已有内容并更新为 `failed`。
- 任务有执行租约。API 重启后恢复排队任务，执行中的任务在租约过期后重新领取，最多领取三次。进程中断可能造成模型重复请求，不保证上游计费幂等；明确的模型错误不自动重试，由用户修正配置后重新生成。
- `GET /api/meetings/events` 为 WebSocket 协议地址，首帧发送 `{token}` 验证 JWT；仅推送当前用户的会议元数据。PostgreSQL LISTEN/NOTIFY 支持多个 API 实例，首次快照覆盖建立连接前任务已完成的情况。列表和详情仅在生成期间订阅，不恢复定时 GET 轮询。
- API 配置 `SIDECAR_API_URL` 和 `SIDECAR_INTERNAL_TOKEN`；Sidecar 配置独立 `ARK_API_KEY`、`ARK_MODEL`，以及相同内部凭证。默认模型按项目指定为 `deepseek-v4-1-flash-261017`。

生产反向代理需要转发 `/api/meetings/events` 的 WebSocket Upgrade，且将客户端页面 Origin 加入 `CORS_ORIGINS`。开发 Vite 和 Electron 内置代理已支持。

## 会议纪要协作与版本

- 原始转写按 `segments` 保存说话人、时间及文本。待生成页面仅供创建者纠错，首次修正会在 `meeting_segments.original_text` 保留识别原文。生成仅使用修正后的转写片段，不读取协作纪要。
- 纪要生成成功后，`meeting_records` 保存 BlockNote / Yjs 状态，初始化时保留标题、列表层级、粗体和表格。协作增量即时合并并持久化到 CRDT 状态；正文按停输 1 秒、持续输入每 5 秒的节奏更新 `meeting_minutes.content/blocks`。思维导图读取最新协作状态，不等待正文快照保存。
- `GET /api/meetings/{id}/record` 读取协作纪要；`POST .../record/share` 获取稳定链接。持链接的同事必须登录，可编辑纪要、查看历史。仅创建者可保存命名版本、恢复版本及归档；归档后所有人只读。
- `/api/meetings/{id}/record/events` 使用 WebSocket，首帧 `{token, share_token?}`。Yjs 增量由 pycrdt 在行锁内合并，增量提交后发送 `ack`；客户端按自动保存节奏发送 `{type:"save", save_seq, epoch}`，正文提交后返回 `saved`，失败返回 `save.error` 并支持同连接重试。`saved_revision/saved_at` 表示已保存的正文版本及时间；成员与光标通过 awareness 同步，跨进程使用 PostgreSQL LISTEN/NOTIFY。
- `GET/POST .../record/versions` 查询最近 100 个版本或保存命名版本；`GET .../versions/{version_id}` 预览；`POST .../versions/{version_id}/restore` 使用 `{expected_revision}` 恢复。编辑中每隔至少 60 秒保留自动快照，恢复前后均保留版本。
- `POST /api/meetings/{id}/minutes/archive` 提交 `{knowledge_base_id}`，由服务端在一个事务内复制最新协作纪要、保存归档版本、更新会议状态。不存在或不属于自己的知识库不会产生部分归档。
- 旧原文协作数据标记为 `original` 并保留；首次初始化新纪要协作时备份旧状态、轮换协作世代。旧原文分享链接失效，原文版本不会混入纪要历史。协作迁移为 `0009_minutes_collaboration`，自动保存标记迁移为 `0010_minutes_autosave`。
- 客户端串行保存正文，失败后按 2–30 秒退避重试，提供手动重试；切换到后台、离开页面、保存命名版本及归档前补保存，连接断开后服务端也补保存已收到的增量。只有正文确认成功才更新“最近保存时间”。
- 单文档协作状态上限 4 MiB。未确认修改暂留页面内存，断网提示待同步、重连后重发；关闭页面前应确认已保存。
- 部署前安装 API 依赖并执行 `alembic upgrade head`。反向代理需转发 `/api/meetings/{id}/record/events` 的 Upgrade。
