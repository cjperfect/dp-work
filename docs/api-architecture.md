# dp-work API 架构设计

> 目标：为 `services/api` 建立企业级分层架构——统一响应协议（`code` / `message` / `data`）、用户认证守卫、请求拦截器（中间件）、异常过滤器（全局异常处理），为后续会议、纪要、知识库、Agent 等业务路由提供一致底座。

## 1. 设计原则

| 原则               | 说明                                                                            |
| ------------------ | ------------------------------------------------------------------------------- |
| 统一响应           | 所有接口（含错误）输出 `{ code, message, data }`，前端据此统一处理，业务码见 §3 |
| 守卫前置           | 认证 / 角色 / 部门校验在路由入口（FastAPI 依赖）完成，业务函数不感知认证细节    |
| 横切集中           | 请求 ID、日志、耗时、认证注入等横切逻辑收口在中间件与依赖，路由只写业务         |
| 异常归一           | 任何异常最终走全局过滤器输出统一格式，不向客户端泄漏堆栈                        |
| 幂等与 append-only | 延续转写分句的幂等设计（ON CONFLICT DO NOTHING）                                |

## 2. 分层架构

当前代码已按业务模块落地，目录及测试命令以 [API README](../services/api/README.md) 为准。
`modules/*/router.py → service.py → repository.py`；连接池和事务工具集中在 `infrastructure/database/session.py`。
已接入 SQLAlchemy 2.x 异步 ORM 与 Alembic，asyncpg 作为 PostgreSQL 驱动。

```
请求 → [CORS] → [拦截器：RequestContext 中间件]
                    │ 生成 X-Request-ID、计时、访问日志、注入 request.state
                    ▼
              [认证守卫：路由/分组级 dependencies]
                    │ Bearer JWT → 解析 → 查库 → request.state.user
                    │ 可选 require_role / require_dept / require_scope
                    ▼
              [路由层 routes] → [服务层 services] → [存储层 db/DAO]
                    │
                    │ 成功：返回 ApiResponse(data=...)；业务失败：raise ApiError
                    ▼
              [过滤器：全局 Exception Handlers]
                    │ ApiError / HTTPException / RequestValidationError / 未知异常
                    ▼
            统一响应 { code, message, data }
```

FastAPI 概念映射（本次规划的关键认知）：

| 传统概念            | FastAPI 落地                                              | 职责                                                      |
| ------------------- | --------------------------------------------------------- | --------------------------------------------------------- |
| 拦截器 Interceptor  | `BaseHTTPMiddleware` / `@app.middleware`                  | 请求前：请求 ID、计时、日志、注入上下文；响应后：耗时统计 |
| 认证守卫 Auth Guard | `Depends(get_current_user)`（路由/分组级 `dependencies`） | Bearer 解析、JWT 校验、用户装载、角色/部门鉴权            |
| 过滤器 Filter       | 全局 `exception_handler`（`register_exception_handler`）  | 异常归一为统一响应，错误码映射，日志记录                  |
| 统一响应体          | 泛型 `ApiResponse[T]` + `response_model`                  | 所有路由输出一致结构                                      |

## 3. 统一响应协议

### 3.1 字段定义

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

- `code`：业务码，`int`。`0` = 成功；非 0 = 失败（见错误码表）。
- `message`：人类可读描述（成功 `ok`，失败为具体原因），前端可直接展示。
- `data`：payload。失败时为 `null`。

### 3.2 泛型定义（`app/core/responses.py`）

```python
from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: T | None = None


def ok(data: T | None = None, message: str = "ok") -> ApiResponse[T]:
    return ApiResponse(code=0, message=message, data=data)
```

路由用法：

```python
@router.post("/segments", response_model=ApiResponse[dict])
async def upsert_segments(batch: SegmentsBatch, _: User = Depends(get_current_user)):
    ...
    return ok({"written": written, "ignored": ignored})
```

### 3.3 错误码段位

| 段位   | 含义            | 示例                                                             |
| ------ | --------------- | ---------------------------------------------------------------- |
| `0`    | 成功            | `0`                                                              |
| `1xxx` | 通用 / 请求错误 | `1001` 参数错误、`1002` 校验失败、`1003` 资源不存在              |
| `2xxx` | 认证 / 授权     | `2001` 未登录、`2002` token 过期、`2003` 无权限、`2004` 凭证错误 |
| `3xxx` | 业务规则        | `3001` 会议不存在、`3002` 纪要未生成、`3003` 状态冲突            |
| `5xxx` | 服务端          | `5000` 内部错误（不向客户端泄漏细节）                            |

### 3.4 错误示例

```json
{ "code": 2001, "message": "未登录或凭证无效", "data": null }
{ "code": 1002, "message": "请求参数校验失败", "data": { "text": ["Field required"] } }
```

## 4. 用户认证守卫

### 4.1 认证模型（PostgreSQL `users` 表草案）

```sql
CREATE TABLE users (
  id          text PRIMARY KEY,            -- 幂等键，如 "u-<uuid4>"
  username    text NOT NULL UNIQUE,        -- 登录名（邮箱或工号）
  password_hash text NOT NULL,             -- pbkdf2_sha256$iterations$salt$hash
  display_name text NOT NULL,
  department  text NOT NULL,               -- 部门标识（专业范畴的载体，如 "product" / "hr"）
  role        text NOT NULL DEFAULT 'member',  -- admin / manager / member
  status      smallint NOT NULL DEFAULT 0, -- 0 正常 / 1 停用
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agent_bindings (              -- 规划：用户/部门 → Agent 绑定
  id text PRIMARY KEY,
  agent_id    text NOT NULL,
  department  text,                        -- 部门级绑定（空 = 全员）
  user_id     text,                        -- 用户级绑定（空 = 不限定个人）
  UNIQUE (agent_id, department, user_id)
);
```

密码哈希：标准库 `hashlib.pbkdf2_hmac("sha256", ...)`（零编译依赖、可审计格式串），避免 bcrypt 在 macOS arm 的编译问题。

### 4.2 JWT 令牌

- 库：`PyJWT`（纯 Python）。
- 载荷：`{ "sub": user.id, "role": user.role, "dept": user.department, "exp": ... }`。
- 环境变量：`JWT_SECRET`（生产必配强随机）、`JWT_ALG=HS256`、`JWT_TTL_SECONDS`（默认 7200）。
- 流程：

```
登录 POST /api/v1/auth/login {username, password}
  → 查 users → pbkdf2 校验 → 签发 access_token（JWT）
  → 2001 未登录 / 2004 凭证错误 / 2003 停用用户
```

### 4.3 守卫依赖（`app/modules/auth/dependencies.py`）

```python
async def get_current_user(
    auth: str = Header(..., alias="Authorization"),
) -> User:
    """认证守卫：Bearer JWT → 解析 → 查库 → 返回当前用户；失败抛 ApiError(2001/2002)"""
    ...

def require_role(*roles: str) -> Callable:
    """角色守卫：Depends(get_current_user) 后校验 role ∈ roles，否则 2003"""
    ...

def require_dept(*depts: str) -> Callable:
    """部门守卫：部门专业范畴隔离（数据可见性），否则 2003"""
    ...
```

- 全局接入：受保护路由组统一声明 `router = APIRouter(dependencies=[Depends(get_current_user)])`，豁免 `/health`、`/api/v1/auth/login`、`/api/v1/auth/refresh`。
- 令牌刷新：`POST /api/v1/auth/refresh`（携带有效旧 token 换新，校验过期时间），可选 refresh_token 方案二期扩展。

## 5. 拦截器（中间件）

### 5.1 RequestContextMiddleware（`app/middleware/request_context.py`）

| 职责       | 实现                                                                                 |
| ---------- | ------------------------------------------------------------------------------------ |
| 请求 ID    | 透传 `X-Request-ID`（无则生成 `uuid4`），注入 `request.state.request_id`，响应头回写 |
| 访问日志   | `method path status duration_ms request_id user_id`（认证后补 user_id）              |
| 耗时统计   | 记录进入/离开时间，写日志（可对接后续监控）                                          |
| 上下文注入 | `request.state.request_id`、`request.state.started_at` 供异常过滤器与业务使用        |

```python
@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info("%s %s %s %.1fms rid=%s uid=%s", request.method, request.url.path, response.status_code, duration_ms, request_id, getattr(request.state, "user_id", "-"))
    response.headers["X-Request-ID"] = request_id
    return response
```

### 5.2 认证上下文注入

守卫成功后设置 `request.state.user` 与 `request.state.user_id`，供日志、鉴权与后续租户隔离使用（中间件不直接做认证，职责单一）。

## 6. 过滤器（全局异常处理）

`app/core/exceptions.py` 注册全局 handler：

| 异常                                   | HTTP      | code   | message（对外）                  |
| -------------------------------------- | --------- | ------ | -------------------------------- |
| `ApiError(code, message, status_code)` | 自定义    | 自定义 | 自定义                           |
| `HTTPException`（第三方）              | 其 status | 按映射 | 其 detail                        |
| `RequestValidationError`               | 422       | `1002` | 请求参数校验失败                 |
| `Exception`（兜底）                    | 500       | `5000` | 服务器内部错误（日志记完整堆栈） |

```python
class ApiError(Exception):
    def __init__(self, code: int, message: str, status_code: int = 400):
        ...

@app.exception_handler(ApiError)
async def api_error_handler(_, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message, "data": None})
```

## 7. 目录结构（`services/api/app/`）

```text
app/
├── main.py                         # 应用装配
├── api_router.py                   # 路由汇总
├── lifespan.py                     # 启动与关闭
├── core/                           # 配置、响应、异常、日志、密码/JWT 基础能力
├── middleware/request_context.py   # 请求上下文
├── infrastructure/
│   ├── database/session.py         # 异步引擎、Session、事务工具
│   ├── storage/                    # 对象存储预留
│   └── integrations/               # 飞书、模型适配预留
└── modules/
    ├── auth/                       # router / schemas / service / dependencies
    ├── users/                      # router / schemas / service / repository / models
    ├── meetings/                   # router / schemas / service / repository / exceptions
    ├── departments/                # 后续业务预留
    ├── agents/
    ├── skills/
    ├── knowledge/
    └── connectors/
```

依赖方向为 Router → Service → Repository，跨模块通过 Service 调用。
Repository 只使用传入 AsyncSession，事务由 Service 管理；`core` 不反向导入业务模块。
ORM 模型位于各模块的 models.py，迁移集中在 services/api/migrations。旧库先核对结构并登记基线，新库执行 alembic upgrade head。

## 8. 路由清单（第一期）

| 路由                            | 方法     | 守卫  | 说明                                   |
| ------------------------------- | -------- | ----- | -------------------------------------- |
| `/health`                       | GET      | 公开  | 健康检查（db up/down）                 |
| `/api/v1/auth/login`            | POST     | 公开  | 登录签发 JWT                           |
| `/api/v1/auth/refresh`          | POST     | 公开  | 刷新令牌                               |
| `/api/v1/auth/users/me`         | GET      | 认证  | 当前用户信息（含部门/角色）            |
| `/api/v1/users`                 | GET/POST | admin | 用户管理                               |
| `/api/v1/segments`              | POST     | 认证  | 转写分句批量幂等写入（现有，改造接入） |
| `/api/v1/meetings`              | GET/POST | 规划  | 会议列表 / 创建（未实现）              |
| `/api/v1/meetings/{id}/minutes` | GET/PUT  | 认证  | 会议纪要读取 / 编辑                    |
| `/api/v1/knowledge`             | GET/POST | 规划  | 知识库资料管理（未实现）               |

## 9. 实施阶段

| 阶段            | 内容                                                      | 验收                                                                |
| --------------- | --------------------------------------------------------- | ------------------------------------------------------------------- |
| P0 响应底座     | `core/responses.py` + `core/exceptions.py` + 全局 handler | 所有现有/新增接口返回 `{code,message,data}`；错误不泄漏堆栈         |
| P1 认证体系     | `users` 表迁移 + `security.py` + `deps.py` + auth 路由    | login 签发 JWT；无 token 访问受保护接口返回 2001；角色/部门守卫生效 |
| P2 拦截器       | `middleware/request_context.py`                           | 访问日志含 rid/uid/耗时；响应头 X-Request-ID                        |
| P3 业务路由接入 | segments 改造 + users/meetings/minutes/knowledge 路由     | 统一响应 + 守卫覆盖全部业务接口                                     |
| P4 测试         | 认证/守卫/异常/响应协议 pytest 用例                       | 冒烟全绿，无 token / 错 token / 越权 / 参数错 / 内部错各场景断言    |

## 10. 验证方式

- 单元：`pytest` + `httpx.AsyncClient(transport=ASGITransport(app))` 直接测路由（无需起服务）。
- 冒烟：curl 依次验证 登录 → 带 token 写 segments → 无 token 401 → 错 token 2001 → 越权 2003 → 参数错 1002 → 未知路径 404（统一格式）。
- 环境：业务表通过 `services/api/migrations/` 中的 Alembic 版本管理；集成测试仅使用显式配置的 TEST_DATABASE_URL。

## 11. 关联设计

- **部门专业范畴**：`users.department` 与 Agent 配置 `department` 对齐，`require_dept` 守卫支撑「Agent 按部门范畴输出」的 API 层约束。
- **会议纪要转知识库**：`minutes.status=2 已发布` 触发知识库入库任务（二期），走同一认证与响应底座。
- **统一响应对接前端**：`@dp-work/api-client` 增加 `unwrap()`（code≠0 抛业务错误），前端统一弹 message。

## 12. 连接器（Connectors）设计决策

> 2026-10-24 记录。连接器页已上线（`/connectors`，飞书 CLI mock + 断开二次确认 Popover），本决策约束后端接入形态。

- **连接器不分 Agent**：连接器本质是账号级授权（如飞书 CLI 绑定企业账号，OAuth 一次授权全局生效），不是「某 Agent 的技能」。不按 Agent 实例化连接器，避免同一账号下各 Agent 割裂授权、连接状态/令牌重复管理。
- **粒度放在权限层**：连接器全局一个实例；「哪个部门/角色能用连接器做什么」由后端权限控制（复用 `require_dept` 守卫体系），不在连接器侧做 Agent 维度拆分。
- **数据模型草案**：`connectors(id, name, type, status, account, access_token_encrypted, connected_at, updated_at)` + 授权记录；使用权限由部门权限表关联，不引入 `connector_agent` 关联表。
- **与技能的区别**：技能按 Agent 安装（`skill_id + agent_id`，前端已按此建模）；连接器按账号授权，二者权限语义不同，前端交互形态也相应区分（技能=按 Agent 的安装列表，连接器=全局的连接开关）。
