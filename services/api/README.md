# API 接口文档

- Swagger UI：`http://localhost:8000/api/docs`（前端代理入口：`http://localhost:3000/api/docs`）。
- OpenAPI JSON：`/api/openapi.json`；ReDoc：`/api/redoc`。
- 接口不带 `/v1`，成功统一返回 HTTP 200。
- 登录返回 token 后，在 Swagger 右上角 **Authorize** 粘贴 token，无需填写 `Bearer` 前缀；受保护接口会自动携带认证头。
- 登录、注册的 `encrypted_password` 需要使用 `/api/auth/encryption-key` 返回的公钥进行 JWE 加密，也可以在前端登录后使用返回的 token 调试其他接口。

## 已接入的知识库接口

通用分页定义位于 `app/core/pagination.py`，数据库分页函数位于 `app/infrastructure/database/pagination.py`。页码从 1 开始，每页默认 20 条，最多 100 条，非法参数返回 422。查询超出末页时保留请求页码，返回空列表及真实总数。

- `POST /api/knowledge-bases`：新增知识库。
- `PUT /api/knowledge-bases/{id}`：修改名称和描述，请求体 `{name, description}`，返回更新后的知识库。
- `DELETE /api/knowledge-bases/{id}`：删除知识库，返回 `{code: 0, message: "知识库删除成功", data: null}`。
- `GET /api/knowledge-bases?q=关键词&page=1&page_size=20`：分页查询当前用户知识库，按名称或描述搜索，按更新时间、ID 倒序返回。
- 上述接口都需要 Bearer token，成功返回 HTTP 200；查询结果的 `data` 包含 `item`、`page`、`page_size`、`total`。无记录时 `item` 为 `[]`，`total` 为 0。
- 只能操作当前用户的知识库；不存在或无权访问时返回 404。修改与删除通过事务提交，修改时自动更新 updated_at。
- 前端知识库新增、查询、编辑和删除均已对接，操作后刷新服务端列表；文档操作暂使用本地模拟数据。

# 数据库迁移

使用 SQLAlchemy 2.x 异步 ORM + Alembic，asyncpg 负责 PostgreSQL 连接。命令在 `services/api` 目录、激活本服务虚拟环境后运行；数据库地址取自本服务 `.env` 的 `DATABASE_URL`，进程环境变量优先。应用启动只初始化连接和缺省管理员，不自动执行 DDL。

## 新建数据库

从零搭建（别人拿到项目）按根目录命令即可，与 NestJS `npm run migration:run` 同一手感：

```bash
pnpm db:up        # docker compose up -d：启动 PostgreSQL 16（含 pgvector），自动建库 dp_work
pnpm migrate      # alembic upgrade head：执行全部迁移（0001_users~0011_chat_messages，一表一文件）自动建表
pnpm dev:api      # 启动 API 服务（uvicorn :8000）
```

根目录 npm scripts（等价 Alembic 命令，在 `services/api` 目录、使用本服务虚拟环境运行）：

| 命令                             | 等价 Alembic                      | 用途                           |
| -------------------------------- | --------------------------------- | ------------------------------ |
| `pnpm migrate`                   | `alembic upgrade head`            | 建表/升级到最新                |
| `pnpm migrate:generate`          | `alembic revision --autogenerate` | 按模型差异生成新迁移           |
| `pnpm migrate:revert`            | `alembic downgrade -1`            | 回退一个版本（可能删表删数据） |
| `pnpm migrate:check`             | `alembic check`                   | 校验模型与数据库无结构差异     |
| `pnpm migrate:current`           | `alembic current`                 | 查看当前版本                   |
| `pnpm migrate:history`           | `alembic history`                 | 查看版本链                     |
| `pnpm db:down` / `pnpm db:reset` | —                                 | 停库 / 清空数据重建            |

数据库地址取自本服务 `.env` 的 `DATABASE_URL`，进程环境变量优先。应用启动只初始化连接和缺省管理员，不自动执行 DDL。

`migrations/versions/` 只保留最终结构基线，每张业务表一个迁移文件（0001_users … 0011_chat_messages，head=0011_chat_messages），空库 `upgrade head` 一键建出全部表；历史演进链归档在 `migrations/archive/` 仅供审计。详见 `migrations/README.md`。

## 接入已有旧库

旧版 `services/api/tests/fixtures/legacy_schema.sql` 创建的数据库已有业务表，没有 Alembic 版本，按下面顺序接入：

```bash
python -m app.infrastructure.database.baseline
alembic current
alembic upgrade head
```

基线命令先检查必需表、字段、类型、默认值、唯一约束和索引。结构一致后登记到当前迁移链 head（`0011_chat_messages`），保留原业务数据和账号密码；结构不一致或已有 Alembic 版本时拒绝登记。额外的非业务表不会被修改。不要直接对未知旧库运行 `alembic stamp head`，以免跳过必要检查。

原 SQL 文件保留为旧版结构快照和兼容性测试输入，后续不再往该文件追加业务表变更。

## 日常修改表结构

1. 修改对应模块的 `models.py`；新增模块模型需在 `app/infrastructure/database/model_registry.py` 注册。
2. 生成版本脚本：

   ```bash
   alembic revision --autogenerate -m "describe schema change"
   ```

3. 检查生成的 upgrade / downgrade，补充必要的数据迁移。自动生成无法可靠识别表名或字段重命名。
4. 在测试库执行并验证，再在目标环境执行：

   ```bash
   alembic upgrade head
   alembic check
   ```

已应用的版本脚本保持不变，后续变更创建新版本。迁移脚本不导入当前业务模型，以便历史迁移可独立重放。

## 常用命令

```bash
alembic current                  # 数据库当前版本
alembic history                  # 版本链
alembic check                    # 检查模型与当前数据库有无结构差异
alembic upgrade head --sql       # 输出 SQL，离线审阅
alembic downgrade -1             # 回退一个版本
```

降级可能删除表或字段及其数据，执行前应检查脚本并备份。初始版本降级会删除三个业务表，保留可能被其他业务使用的 vector 扩展。

## 集成验证

```bash
TEST_DATABASE_URL=postgresql://test_user:test_password@127.0.0.1:55432/test_db \
  .venv/bin/python -m pytest tests -q
```

必须显式指定专用测试库，不回退到应用数据库。测试自动执行升级，并验证迁移升降级、模型一致性、旧库基线登记、结构漂移拒绝、批量写入去重与事务回滚。

## 用户主键与迁移

用户主键统一使用 `BIGINT GENERATED ALWAYS AS IDENTITY`，接口中的 `id` 为数字。
主键递增不保证连续，Repository 插入用户时不手动分配 ID。

JWT 的 `sub` 为数字主键的字符串表示，`uidv=2` 标识当前用户身份格式。
无版本的历史令牌已停止支持，需要重新登录；已有数字 ID 令牌继续可用。
浏览器资料统一按 `user:数字ID` 隔离，不依赖其他账号字段。
当前开发浏览器的旧知识库已复制到新命名空间，原始副本保留；其他浏览器的历史资料不会自动迁移。

旧库基线检查使用 `infrastructure/database/legacy_schema.py`（代理当前模型元数据），
已纳入 Alembic 的数据库执行 `alembic upgrade head`。单表迁移降级按版本链逆序删除表。

## 用户显示与更新时间

用户表与接口移除 `display_name`，前端显示 `username`。
`updated_at` 为非空带时区时间戳，新用户默认当前时间，原用户回填 `created_at`。
数据库触发器在用户记录实际变更时自动更新，包括后续修改密码、冻结和解冻。
登录、读取与重复赋相同值不会更新时间；相关管理接口后续实现。

`app/modules/users/constants.py` 集中定义角色、状态名称。
登录用户通过 `GET /api/users/options` 获取字典，前端按代码映射显示：
`roles = {"admin": "管理员", "member": "成员"}`，`statuses = {"0": "正常", "1": "冻结"}`。

## 知识库接口

新增 `app/modules/knowledge`，按 Router → Service → Repository 分层，所有请求使用 Bearer JWT。
当前实现个人知识库：归属从登录用户取得，所有查询、更新和删除同时限定 `owner_id`。
他人资源与不存在的资源统一返回 404，客户端不能提交或修改 owner_id。

| 方法   | 路径                            | 用途                             |
| ------ | ------------------------------- | -------------------------------- |
| GET    | `/api/knowledge-bases?q=关键词` | 当前用户列表，可按名称、描述搜索 |
| POST   | `/api/knowledge-bases`          | 创建，提交 `{name, description}` |
| GET    | `/api/knowledge-bases/{id}`     | 详情                             |
| PUT    | `/api/knowledge-bases/{id}`     | 修改名称和描述                   |
| DELETE | `/api/knowledge-bases/{id}`     | 删除知识库及其文档记录           |

响应沿用 `{code, message, data}`；成功统一返回 HTTP 200（包括创建）。资源包含数字 id、owner_id、name、description、created_at、updated_at。
名称去除首尾空白后不能为空；描述默认为空字符串；搜索中的 `%`、`_` 按字面匹配。

`knowledge_bases`：BIGINT IDENTITY 主键、用户外键、名称、描述、创建与更新时间。
`knowledge_documents`：BIGINT IDENTITY 主键、知识库外键、创建人外键、名称、md/pdf 类型、
upload/editor 来源、storage_key、可选 Markdown content、size_bytes、创建与更新时间。
源文件后续放文件目录或对象存储，数据库存路径及元数据；在线 Markdown 可保存在 content。
两张表均由触发器在实际修改时维护 updated_at。知识库按 owner_id / updated_at / id 索引，文档按 knowledge_base_id / updated_at / id 索引。
删除知识库通过外键级联删除文档行，用户删除受外键限制；文件对象清理须在文件服务接入时实现。

这一步仅开放知识库接口，文档表已建，上传、在线编辑和文档管理接口后续实现。
前端知识库目录改为请求后端，不再写入 IndexedDB。原 IndexedDB 数据保留，但不自动导入 PostgreSQL；
原上传文件仍在 localStorage，跨设备同步目前仅适用于知识库名称、描述等元数据。

迁移命令：`cd services/api && .venv/bin/python -m alembic upgrade head`。
`0005` 降级会删除知识库、文档表及其中数据，需要先备份。

## 手动会议闭环（0006_meeting_workspace）

当前支持会议列表、标题/时间/参会人、手动记录、暂停/恢复、结束确认、Markdown 纪要草稿、导出及归档。
不自动录音，不启动模拟 ASR，也不生成 AI 内容；临时文字通过输入区演示，确认后成为带说话人与相对时间的片段。

- `GET/POST /api/meetings`：个人会议列表和创建，列表支持 q / status。
- `PATCH/DELETE /api/meetings/{id}`：重命名和删除。
- `GET/PUT /api/meetings/{id}/workspace`：恢复与增量批次同步。
- `POST /api/meetings/{id}/archive`：将已结束会议的已保存纪要归档。
- `GET /api/knowledge-bases/{id}/documents`：受权限保护的知识库文档阅读。

`meetings` 使用独立 UUID 字符串 ID，改名不影响关联；owner_id 外键引用 users 数字 ID。
status 为 active / paused / ended / archived，elapsed_ms 与 resumed_at 共同保存计时基准，刷新不重置计时。
会议修订号 revision 用于冲突检测；工作区更新带 expected_revision 和 sync_id，事务中锁定会议行。
同批 sync_id 的重试不重复写入；最多 200 个确认片段一批，临时文字不上传。
既有 /segments 与 /minutes 接口也按会议归属隔离，写入会使 revision 递增。

浏览器端会议与知识库目录的持久化方式不同：会议需要断网恢复，草稿及 outbox 存在 IndexedDB
`dp-meeting-workspaces`，按用户数字 ID 与会议 ID 隔离。Zustand 仅缓存当前工作区。
本地事务提交后才显示“本地已保存”；应用壳每 5 秒及网络恢复时从持久化 outbox 同步。
发出前先持久化批次载荷，响应丢失后复用同一 sync_id；同步期间输入的新文字保留到下一批。
未确认输入只在本地保存，结束会议时自动确认为片段。实际本地存储失败会明确提示，不能显示同步成功。
现代浏览器通过 Web Locks 对同一会议限制一个编辑页面，其他页面只读，释放后自动取得编辑权。
不同设备发生修订冲突时不覆盖服务端；用户可下载完整本地恢复副本，再载入服务器版本。
会话过期后停止请求并保留本地草稿；本地数据属于浏览器站点存储，用户清理站点数据会将其移除。
Electron 的 SQLite/IPC 实现后续替换该存储适配层。

纪要归档前先排空该会议待同步批次。知识库服务在同一事务内检查目标归属、保存 Markdown 文档、
更新 minutes.archived_document_id、会议状态及修订号。重复归档更新同一文档；切换到其他知识库返回冲突。
导出 Markdown 和原始记录插入均由用户点击触发，未接入自动摘要。
删除会议级联删除转写及纪要，已归档知识库文档独立保留；删除知识库后关联归档文档指针置空。

迁移保留早期无法推断用户归属的纪要/转写数据，不任意分配管理员，也不在个人接口暴露。
新增外键以 NOT VALID 保护旧行，新写入必须关联真实会议；归属确认后再迁移旧行并验证约束。
`0006` 降级删除会议表并解除新关联，升级/降级均应先备份。
前端验证：`pnpm --filter @dp-work/web test:meetings`。

## Agent 配置与会话

当前范围为 Agent 信息、关联配置、会话管理与消息/上下文保存，使用 assistant-ui ExternalStoreRuntime。
输入框不调用 `/api/chat`，本次不触发模型、技能安装或执行，也不会插入模拟模型回答。

- `GET /api/agents`：当前用户的 Agent 与可关联技能目录，首次幂等创建 general / product。
- `PUT /api/agents/{code}`：名称、部门、介绍、默认知识库和技能关联；携带 expected_revision 防覆盖。
- `GET/POST /api/agents/{code}/threads`：列表/创建会话，列表支持 q；创建使用客户端 UUID 作为幂等键。
- `GET/PATCH/DELETE /api/agents/{code}/threads/{id}`：恢复、重命名与删除。
- `POST .../{id}/activate`：恢复会话并保存该 Agent 的当前会话指针。
- `PUT .../{id}/draft`：草稿及已选知识库，携带草稿 expected_revision。
- `POST .../{id}/messages`：保存用户消息及上下文快照，消息 UUID 允许丢失响应后安全重试。

新增 agents、agent_knowledge_bases、chat_threads、chat_thread_knowledge_bases、chat_messages 五张表。
Agent 以 owner_id + code 唯一；会话通过 agent_id 推导归属，每个读写都验证当前用户和 Agent。
知识库关联采用外键，知识库删除时自动清除当前关联；用户消息中的名称与技能快照保留历史事实。
技能目录目前为内置配置项，关联 ID 保存在 Agent 的 JSONB 字段；后续由技能注册/安装服务扩展。

新会话继承 Agent 默认知识库。已有会话可独立增减上下文，修改默认配置不会改写既有会话。
输入 @ 后搜索当前用户的知识库，支持 ↑↓ / Enter / Escape，中文输入法确认不触发误发送。
选中后移除输入中的 @ 查询片段，将知识库显示成可移除标签；实际消息正文不拼接知识库名称。
每条消息保存当时的知识库 ID/名称、技能以及 Agent 信息与配置修订号，供执行服务后续读取。
会话切换和 Agent 切换使用独立 assistant-ui runtime，消息、输入状态、配置及选择不会混用。
侧栏搜索限定当前 Agent 会话，刷新从后端恢复每个 Agent 的当前会话和已保存草稿。

草稿输入在 600ms 停顿后自动保存到服务器，切换会话/新建/发送前会先等待草稿保存。
Agent 与聊天不使用 IndexedDB/localStorage 存储业务数据；Zustand 仅作内存缓存。
网络失败时保留当前页面草稿并提示重试，只有后端确认的内容可以在刷新后恢复。
草稿版本冲突不会覆盖服务器内容，用户应保留当前文本后重新载入；本次不提供离线聊天队列。

删除会话会级联删除消息、草稿与会话上下文，不删除 Agent 或知识库。
迁移在 0009_chat_threads 显式补上 agents.active_thread_id 的循环外键，升降级均可重放。
前端验证：`pnpm --filter @dp-work/web test:agent`。
