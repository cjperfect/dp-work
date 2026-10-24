# 企业 Agent 平台 API

FastAPI 模块化单体。按业务组织代码，统一认证、响应格式、异常处理和请求日志。
使用 SQLAlchemy 2.x 异步 ORM、asyncpg 驱动和 Alembic 版本迁移，保留现有 HTTP URL 与业务表结构。

## 目录与职责

```text
app/
├── main.py                     # create_app：应用装配
├── api_router.py               # 汇总路由、健康检查、404
├── lifespan.py                 # 资源启动和关闭
├── decorators/                 # 按用途组织的 HTTP 装饰器
│   ├── __init__.py             # 统一导出
│   └── auth.py                 # require_user：登录、角色、部门校验
├── core/
│   ├── config.py               # 本服务 .env、数据库/JWT/CORS 配置
│   ├── exceptions.py           # 通用异常和 HTTP 异常映射
│   ├── responses.py            # ApiCode、ApiResponse、ok
│   ├── security.py             # 密码哈希、JWT 基础能力
│   └── logging.py              # 日志配置
├── middleware/
│   └── request_context.py      # 请求 ID、耗时、访问日志
├── infrastructure/
│   ├── database/
│   │   ├── base.py            # ORM 基类和约束命名
│   │   ├── session.py         # 异步引擎、Session、事务边界
│   │   ├── model_registry.py  # 统一注册 ORM 模型供迁移使用
│   │   └── baseline.py        # 核对旧库并登记基线
│   ├── storage/                # 对象存储适配预留
│   └── integrations/           # 飞书、模型服务适配预留
└── modules/
    ├── auth/                   # 注册、登录、刷新、当前用户、认证依赖
    ├── users/                  # 用户模型、账号管理
    ├── meetings/               # 转写分句、会议纪要
    ├── departments/            # 以下为职责明确的预留模块
    ├── agents/
    ├── skills/
    ├── knowledge/
    └── connectors/
migrations/                     # Alembic 环境、版本脚本与迁移说明
tests/
├── unit/                       # 模块边界约束
├── api/                        # 无外部数据库的 HTTP 行为测试
└── integration/                # 专用 PostgreSQL 集成测试
```

活跃模块按需包含：

- `router.py`：接收 HTTP 参数、注入身份、包装响应。禁止直接访问数据库。
- `schemas.py`：Pydantic 请求/响应协议。
- `service.py`：业务规则与事务边界，不依赖 FastAPI。
- `repository.py`：SQLAlchemy 查询与持久化，只使用传入 Session，不创建 Session 或提交事务。
- `models.py`：SQLAlchemy 声明式 ORM 模型；不承担业务查询。
- `exceptions.py`：模块业务异常。

认证本身不拥有用户表，因此调用 `users.service`，不重复创建 Repository 或用户模型。
预留模块没有虚构的业务接口，真正实现时再补对应文件。

## 依赖规则

```text
HTTP Router → Service → Repository → PostgreSQL
                  ↓
       infrastructure 中的外部服务适配器
```

1. 跨模块使用公开 Service；禁止直接访问其他模块 Repository。
2. Service 决定事务范围。外部 HTTP、模型推理不在数据库事务内等待。
3. `core` 不导入业务模块，防止公共目录形成反向依赖。
4. 密码只在 Service 中哈希；Repository 接收哈希，不接收明文密码。
5. 数据库访问统一经过 `infrastructure.database.session`，业务模块不自行创建连接池。
6. API 的 PG 数据模型与 Sidecar 的 SQLite 模型分别维护，通过通信协议关联。

`tests/unit/test_boundaries.py` 自动检查主要依赖约束。

## 用户校验装饰器

统一从 `app.decorators` 导入，装饰器放在路由装饰器下方：

```python
from app.decorators import require_user

@router.get("/example")
@require_user()
async def example():
    return {"ok": True}

@router.post("/finance/example")
@require_user(roles=("admin", "manager"), departments=("finance",))
async def finance_example():
    return {"ok": True}
```

`require_user()` 校验 JWT、账号存在且启用；权限使用数据库中的当前角色和部门。同类条件满足任意一个，角色与部门同时指定时须同时满足。未认证返回 401，无权限返回 403，沿用统一错误响应。
当前用户可通过 `request.state.user` 获取，或保留 `Annotated[User, Depends(get_current_user)]` 参数注入，同请求复用用户查询结果。支持同步、异步 HTTP 路由，不用于 Service 或普通函数调用。

用户管理和会议业务路由已使用此装饰器；登录、注册等公开接口保持原访问规则。后续装饰器在 `app/decorators/` 按用途增加文件，并在 `__init__.py` 导出。

## 启动

```bash
cd services/api
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
cp .env.example .env
alembic upgrade head   # 空库首次建表，或已登记版本的库升级
uvicorn app.main:app --port 8000
```

配置从本服务的 `.env` 加载，进程中已设置的变量优先。
API 启动时默认创建管理员：用户名 `chenjiang`，密码 `chenjiang`，角色 `admin`。
只创建不存在的账号，重复启动不会覆盖已有密码或提升已有账号权限。
可通过 `BOOTSTRAP_ADMIN_ENABLED=0` 关闭初始化，或用 `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` 设置初始凭证。
业务表统一由 Alembic 管理，应用启动不自动建表或执行迁移。
如果数据库已有旧版业务表但尚无 Alembic 版本，先运行 `python -m app.infrastructure.database.baseline`；该命令核对结构一致后登记基线，保留原数据，再运行 `alembic upgrade head`。结构不一致会拒绝登记。
详细流程见 [数据库迁移说明](migrations/README.md)。原 `infra/postgres/init/01-init.sql` 仅保留为旧版结构快照和兼容性测试输入。

## 保留的接口

| 接口                                          | 用途             | 权限               |
| --------------------------------------------- | ---------------- | ------------------ |
| `POST /api/v1/auth/register`                  | 用户名密码注册   | 公开，固定普通成员 |
| `POST /api/v1/auth/login`                     | 登录             | 公开               |
| `POST /api/v1/auth/refresh`                   | 刷新令牌         | 有效令牌           |
| `GET /api/v1/auth/users/me`                   | 当前用户         | 登录               |
| `GET /api/v1/users`                           | 用户列表         | admin              |
| `POST /api/v1/users`                          | 创建用户         | admin              |
| `POST /api/v1/segments`                       | 批量追加转写片段 | 登录               |
| `GET /api/v1/minutes`                         | 纪要列表         | 登录               |
| `GET /api/v1/meetings/{id}/minutes`           | 读取纪要         | 登录               |
| `PUT /api/v1/meetings/{id}/minutes`           | 编辑纪要         | 登录               |
| `POST /api/v1/meetings/{id}/minutes/generate` | 现有生成占位入口 | 保留公开占位行为   |
| `GET /health`                                 | 数据库健康检查   | 公开               |

业务接口响应为 `{code, message, data}`，健康检查保持 `{ok, db}`。
分句批量写入最多 200 条，`data` 返回 `{written, ignored}`，按片段 ID 去重。
现有部门/角色守卫已迁至 `modules/auth/dependencies.py`；会议资源级权限需随会议成员模型实现。

## 验证

```bash
# 默认仅执行无外部数据库的测试
.venv/bin/python -m pytest -q

# 显式指定专用测试数据库，执行真实 PG 集成测试
TEST_DATABASE_URL=postgresql://test_user:test_password@127.0.0.1:55432/test_db \
  .venv/bin/python -m pytest tests/integration -q

# 全部测试（同样必须显式指定测试库）
TEST_DATABASE_URL=postgresql://test_user:test_password@127.0.0.1:55432/test_db \
  .venv/bin/python -m pytest tests -q
```

集成测试会先执行 `alembic upgrade head`，再创建并清理测试记录及隔离测试 schema；请使用专用空库或已登记 Alembic 版本的测试库。未设置 `TEST_DATABASE_URL` 时跳过，不回退到应用数据库。
