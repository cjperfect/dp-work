# 数据库迁移

使用 SQLAlchemy 2.x 异步 ORM + Alembic，asyncpg 负责 PostgreSQL 连接。命令在 `services/api` 目录、激活本服务虚拟环境后运行；数据库地址取自本服务 `.env` 的 `DATABASE_URL`，进程环境变量优先。应用启动只初始化连接和缺省管理员，不自动执行 DDL。

## 迁移体系（squash 后）

`versions/` 只保留**最终结构基线**：每张业务表一个迁移文件，按依赖顺序链式执行，空库 `upgrade head` 即一键建出全部表。

| 版本                             | 表                                                    |
| -------------------------------- | ----------------------------------------------------- |
| 0001_users                       | users（含 updated_at 触发器函数）                     |
| 0002_meetings                    | meetings                                              |
| 0003_transcript_segments         | transcript_segments                                   |
| 0004_knowledge_bases             | knowledge_bases（含 updated_at 触发器函数）           |
| 0005_knowledge_documents         | knowledge_documents                                   |
| 0006_minutes                     | minutes                                               |
| 0007_agents                      | agents                                                |
| 0008_agent_knowledge_bases       | agent_knowledge_bases                                 |
| 0009_chat_threads                | chat_threads（并补 agents.active_thread_id 循环外键） |
| 0010_chat_thread_knowledge_bases | chat_thread_knowledge_bases                           |
| 0011_chat_messages               | chat_messages（head）                                 |

历史演进链（原 `0001_initial`~`0007_agents_chat` 的字段变更步骤，如主键升级、删除 display_name / legacy_id 等）已压缩进最终建表语句，不再作为独立迁移存在。旧脚本归档在 `migrations/archive/`（含 git 中恢复的最初版 `0001_initial_legacy.py`），仅供审计，不参与执行。

## 新建数据库

先启动 PostgreSQL（镜像包含 pgvector），再执行：

```bash
alembic upgrade head
uvicorn app.main:app --port 8000
```

根目录也提供快捷方式：`pnpm db:up && pnpm migrate && pnpm dev:api`（见根 `package.json` 与 `services/api/README.md`）。

## 接入已有旧库

旧库（已有业务表、没有 Alembic 版本号）按下面顺序接入：

```bash
python -m app.infrastructure.database.baseline
alembic current
alembic upgrade head
```

基线命令先检查必需表、字段、类型、默认值、唯一约束和索引。结构一致后登记到当前迁移链 head（`0011_chat_messages`），保留原业务数据和账号密码；结构不一致或已有 Alembic 版本时拒绝登记。额外的非业务表不会被修改。不要直接对未知旧库运行 `alembic stamp head`，以免跳过必要检查。

旧版结构快照保留在 `services/api/tests/fixtures/legacy_schema.sql`，仅作为兼容性测试输入，后续不再往该文件追加业务表变更。

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
alembic heads                    # 当前链的 head
alembic check                    # 检查模型与当前数据库有无结构差异
alembic upgrade head --sql       # 输出 SQL，离线审阅
alembic downgrade -1             # 回退一个版本
```

降级会按版本链逆序删除表（DROP ... CASCADE 仅删本表及其依赖），执行前应检查脚本并备份。

## 集成验证

```bash
TEST_DATABASE_URL=postgresql://test_user:test_password@127.0.0.1:55432/test_db \
  .venv/bin/python -m pytest tests -q
```

必须显式指定专用测试库，不回退到应用数据库。测试自动执行升级，并验证：空库升级/降级/模型一致性、旧库基线登记、结构漂移拒绝、批量写入去重与事务回滚。

## 最终结构要点

- **用户主键**：`BIGINT GENERATED ALWAYS AS IDENTITY`，接口 `id` 为数字，递增不保证连续；JWT `sub` 为数字主键字符串，`uidv=2` 标识当前身份格式。`display_name`、`legacy_id` 已从最终结构移除。
- **updated_at 触发器**：users / knowledge_bases / knowledge_documents 由数据库触发器在记录实际变更时自动更新（`old.* IS DISTINCT FROM new.*`），登录、读取、重复赋相同值不会更新时间。
- **会议与纪要**：status 为 active / paused / ended / archived；elapsed_ms 与 resumed_at 共同保存计时基准。minutes 与 transcript_segments 的 meeting_id 外键语义为级联删除。
- **Agent 会话**：agents.active_thread_id 与 chat_threads.agent_id 为循环外键，建表时显式拆开（agents 表先建，循环外键在 0009 补上），升降级均可重放。
- **知识库文档**：knowledge_documents.file_type 约束为 `md` / `pdf`，source 约束为 `upload` / `editor`，name 非空、size_bytes 非负。
