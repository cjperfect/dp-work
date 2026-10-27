# 数据库迁移

API 使用 PostgreSQL、SQLAlchemy 2.x 异步 ORM、asyncpg 和 Alembic。连接地址读取 `services/api/.env` 的 `DATABASE_URL`，进程环境变量优先。API 启动不会自动建表。

## 新环境

在仓库根目录执行：

```bash
pnpm db:up
pnpm migrate
pnpm dev:api
```

Docker Compose 提供 PostgreSQL 16（镜像包含 pgvector，当前业务尚未启用向量扩展），开发库为 `dp_work`，账号、密码均为 `chenjiang`，端口为 `127.0.0.1:5432`。数据库持久化在 Docker volume 中。生产环境通过服务端 `.env` 配置连接信息。

## 当前迁移链

| 版本                     | 内容                               |
| ------------------------ | ---------------------------------- |
| 0001_users               | 用户                               |
| 0002_knowledge_bases     | 知识库                             |
| 0003_knowledge_documents | 文档及富文本结构                   |
| 0004_document_uploads    | 上传源文件元数据                   |
| 0005_meetings            | 会议、确认转写、纪要               |
| 0006_meeting_timestamp   | 会议生成毫秒时间戳改为 BIGINT      |
| 0007_minutes_generation  | 持久化生成任务、输入快照及来源版本 |

历史 `archive/` 仅供参考，不参与当前迁移。

## 修改结构

修改模块 `models.py`；新模型在 `src/infrastructure/database/model_registry.py` 注册，然后执行：

```bash
pnpm migrate:generate -- -m describe_change
pnpm migrate
pnpm migrate:check
```

生成后先审阅脚本。已经应用的脚本不再修改，新增迁移承接变化。降级可能删除数据，执行前备份；`0006` 降级会清除无法放入 INTEGER 的旧版模拟生成计时值。

## 从 SQLite 导入

先对空 PostgreSQL 执行 `alembic upgrade head`，暂停 API 写入，然后在 `services/api` 目录执行：

```bash
.venv/bin/python scripts/import_sqlite.py data/dp_work.db
```

目标地址仍从 `DATABASE_URL` 读取。导入保留主键、时间、富文本 JSON 和密码哈希，修复自增序列；所有业务行在一个事务中写入。目标业务表非空时拒绝覆盖。源 SQLite 只读、不删除，上传源文件继续使用原存储目录；部署到另一台服务器时须另行迁移源文件和服务端密钥。

## 集成测试

必须指定独立 PostgreSQL 测试库，不使用业务库：

```bash
TEST_DATABASE_URL=postgresql+asyncpg://chenjiang:chenjiang@127.0.0.1:5432/dp_work_test \
  .venv/bin/python -m pytest tests/unit tests/api tests/integration -q
```

测试验证迁移升降级、模型一致性、事务回滚、账号隔离、文档及会议持久化。迁移冒烟测试账号需要创建和删除临时测试数据库的权限。
