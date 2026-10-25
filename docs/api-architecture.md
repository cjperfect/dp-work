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
已接入 SQLAlchemy 2.x 异步 ORM 与 Alembic，aiosqlite 作为 SQLite 驱动。

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

### 4.1 认证模型（SQLite `users` 表）

```sql
CREATE TABLE users (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  username    text NOT NULL UNIQUE,        -- 登录名（邮箱或工号）
  password_hash text NOT NULL,             -- pbkdf2_sha256$iterations$salt$hash
  department  text NOT NULL,               -- 部门标识（专业范畴的载体，如 "product" / "hr"）
  role        text NOT NULL DEFAULT 'member',  -- admin / member
  status      smallint NOT NULL DEFAULT 0, -- 0 正常 / 1 冻结
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now() -- 更新由数据库触发器维护
);

CREATE TABLE agent_bindings (              -- 规划：用户/部门 → Agent 绑定
  id text PRIMARY KEY,
  agent_id    text NOT NULL,
  department  text,                        -- 部门级绑定（空 = 全员）
  user_id     bigint REFERENCES users(id), -- 用户级绑定（空 = 不限定个人）
  UNIQUE (agent_id, department, user_id)
);
```

密码哈希：标准库 `hashlib.pbkdf2_hmac("sha256", ...)`（零编译依赖、可审计格式串），避免 bcrypt 在 macOS arm 的编译问题。

### 4.2 JWT 令牌

- 库：`PyJWT`（纯 Python）。
- 载荷：`{ "sub": str(user.id), "uidv": 2, "role": user.role, "dept": user.department, "exp": ... }`。
- 令牌按数字主键查询；只接受 `uidv=2` 的身份格式，无版本历史令牌需要重新登录。
- 环境变量：`JWT_SECRET`（生产必配强随机）、`JWT_ALG=HS256`、`JWT_TTL_SECONDS`（默认 604800，即一周）。
- 流程：

```
登录 POST /api/auth/login {username, encrypted_password}
  → JWE 解密 → 查 users → pbkdf2 校验 → 签发 access_token（JWT）
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

- 全局接入：受保护路由组统一声明 `router = APIRouter(dependencies=[Depends(get_current_user)])`，豁免 `/health`、`/api/auth/login`、`/api/auth/refresh`。
- 令牌刷新：`POST /api/auth/refresh`（携带有效旧 token 换新，校验过期时间），可选 refresh_token 方案二期扩展。

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

| 路由                         | 方法     | 守卫  | 说明                                   |
| ---------------------------- | -------- | ----- | -------------------------------------- |
| `/health`                    | GET      | 公开  | 健康检查（db up/down）                 |
| `/api/auth/login`            | POST     | 公开  | 登录签发 JWT                           |
| `/api/auth/refresh`          | POST     | 公开  | 刷新令牌                               |
| `/api/users`                 | GET/POST | admin | 用户管理                               |
| `/api/segments`              | POST     | 认证  | 转写分句批量幂等写入（现有，改造接入） |
| `/api/meetings`              | GET/POST | 规划  | 会议列表 / 创建（未实现）              |
| `/api/meetings/{id}/minutes` | GET/PUT  | 认证  | 会议纪要读取 / 编辑                    |
| `/api/knowledge`             | GET/POST | 规划  | 知识库资料管理（未实现）               |

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

## 知识库接口（0005_knowledge）

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
前端知识库目录改为请求后端，不再写入 IndexedDB。原 IndexedDB 数据保留，但不自动导入 SQLite；
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

## Agent 配置与会话（0007_agents_chat）

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
迁移显式拆开 agents.active_thread_id 与 chat_threads.agent_id 的循环外键，升降级均可重放。
`0007` 降级会删除本模块五张表和数据，执行前应备份。
前端验证：`pnpm --filter @dp-work/web test:agent`。
