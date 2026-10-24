# 数据库迁移

使用 SQLAlchemy 2.x 异步 ORM + Alembic，asyncpg 负责 PostgreSQL 连接。命令在 `services/api` 目录、激活本服务虚拟环境后运行；数据库地址取自本服务 `.env` 的 `DATABASE_URL`，进程环境变量优先。应用启动只初始化连接和缺省管理员，不自动执行 DDL。

## 新建数据库

先启动 PostgreSQL（镜像包含 pgvector），再执行：

```bash
alembic upgrade head
uvicorn app.main:app --port 8000
```

初始版本 `0001_initial` 创建 users、minutes、transcript_segments 及索引。Docker 初始化目录 `infra/postgres/bootstrap` 仅启用 vector 扩展，业务表由迁移管理。

## 接入已有旧库

旧版 `infra/postgres/init/01-init.sql` 创建的数据库已有业务表，没有 Alembic 版本，按下面顺序接入：

```bash
python -m app.infrastructure.database.baseline
alembic current
alembic upgrade head
```

基线命令先检查必需表、字段、类型、默认值、唯一约束和索引。结构一致后只登记 `0001_initial`，保留原业务数据和账号密码；结构不一致或已有 Alembic 版本时拒绝登记。额外的非业务表不会被修改。不要直接对未知旧库运行 `alembic stamp head`，以免跳过必要检查。

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
