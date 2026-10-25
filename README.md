# dp-work

企业 Agent 平台（Desktop-first · Local-first）monorepo。

## 背景

dp-work 是一套**企业 Agent 工作台 + 会议智能化**平台：团队成员在统一的 Agent 聊天界面（支持模型切换、知识库问答、工具调用可视化）里协作，同时内置完整会议链路——**实时转写（ASR）→ AI 会议纪要 → 历史归档**。

架构遵循 **local-first** 原则：转写分句先落本地（实时、离线可用），再经 outbox 队列批量幂等同步到本地 SQLite（单文件、零依赖），兼顾桌面端流畅体验与数据一致性。最终形态为 Electron 桌面应用 + Web 端双入口。

**Agent 的作用**：根据**部门专业范畴**和 **SOP**，以及对应的 **Skills** 来输出结果——部门专业范畴界定职责边界（不越界回答），SOP 标准作业流程约束推理与执行步骤，对应 Skills 决定可用工具与话术。三者建模为 Agent 配置（department / sop / skills）：会话启动时组装为系统提示并挂载工具集，输出前做范畴与 SOP 合规检查。此外 Agent 可**对接用户创建的知识库**（RAG 语义检索），作答时引用库内资料；**会议纪要生成后可发布转入知识库**，沉淀为团队可检索的资料资产。

## 已开发功能点

### ✅ 已开发

| 模块                 | 功能                                    | 说明                                                                                                                                                                                                                                                           |
| -------------------- | --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Agent 工作台**     | 通用 Agent / 产品 / 技能 / 知识库多入口 | 路由：`/`、`/product`、`/skills`、`/knowledge`                                                                                                                                                                                                                 |
|                      | assistant-ui 聊天界面                   | 消息流、模型切换器（Sonnet / GPT / Gemini + 品牌图标）、会话地图（右侧栏）、日期分隔、Directive 指令文本、Markdown 渲染、Shiki 语法高亮、Mermaid 图、引用块、工具调用 / 回退 UI                                                                                |
|                      | 状态管理                                | zustand：agentId、启用知识库、当前模型、会议标题、会议状态（live / generating）                                                                                                                                                                                |
| **会议模块**         | 开始会议                                | 单按钮 + 标题弹窗，一键进入会议页                                                                                                                                                                                                                              |
|                      | 实时转写页（`/meetings/active`）        | 麦克风采集 PCM16，经 Sidecar 对接豆包双向流式识别；展示临时文字、确认片段和说话人，支持暂停、恢复和结束等待尾句。                                                                                                                                              |
|                      | 会话持久化                              | sessionStorage 恢复：刷新 / 切换路由不丢计时与已转写内容（离开拦截 confirm：取消不刷新）                                                                                                                                                                       |
|                      | 会议列表页（`/meetings`）               | 「会议纪要 AI 生成中」区块（结束会议后进入生成中态 + 测试数据）+「历史会议」区块（查看会议纪要入口）                                                                                                                                                           |
| **转写同步体系**     | 豆包流式 ASR 分句确认                   | 已接入真实 WebSocket 协议；未确认片段原子保存到 `.dp-work/temp/asr`，确认片段先写 SQLite 再推送前端。实际服务连通性待填写凭证后验证。                                                                                                                          |
|                      | 前端本地实时保存                        | IndexedDB 模拟 SQLite（`dp-work-local`）：一分句一行 + outbox pending 标记；Electron 期无缝换 better-sqlite3                                                                                                                                                   |
|                      | Web ⇄ Sidecar WS 对接                   | `useMeetingAsr` hook：连接生命周期、StrictMode 时序竞态已修复、协议类型共享                                                                                                                                                                                    |
| **后端服务**         | sidecar（:8001）                        | FastAPI WebSocket + SQLite 本地存储 + 豆包 ASR 适配；会议 API 批量同步尚未接入。                                                                                                                                                                               |
|                      | api（:8000）                            | FastAPI + SQLAlchemy 2.x + Alembic（aiosqlite）；**统一响应 `{code,message,data}`** + **JWT 认证守卫**（登录/刷新、require_role/require_dept）+ RequestContext 中间件（X-Request-ID/日志/耗时）+ 全局异常过滤器；SQLite 单文件存储 `users` / `knowledge_bases` |
| `@dp-work/contracts` | `packages/contracts`                    | Web ↔ Sidecar 的 camelCase 消息、转写分句及桌面 IPC 类型定义。                                                                                                                                                                                                 |
|                      | `@dp-work/api-client`                   | 浏览器 / Node 通用 API 客户端：批量上行分句、健康检查                                                                                                                                                                                                          |
| **工程化**           | Monorepo                                | pnpm workspace；ESLint / Prettier 根配置统一收口（子包零配置继承）；Commitlint + Husky + lint-staged                                                                                                                                                           |

### 🚧 规划中 / 待接入

| 事项                                            | 状态                                                                                                                                                    |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 豆包真实服务联调                                | 接入代码和本地模拟上游测试已完成，待填写有效语音服务凭证后验证。无需额外安装旧版 Ark SDK。                                                              |
| 前端 outbox → api 定时上行                      | `@dp-work/api-client` 已就绪，待接线（api + SQLite 已可写）                                                                                             |
| AI 会议纪要生成链路                             | `minutes` 表已建（status 预留 2=已发布到知识库）；`/meetings/minutes` 页面为占位待设计；纪要支持发布转入知识库                                          |
| 知识库上传 / 解析 / 向量化                      | RAG 检索链路预留；Agent 可绑定知识库（RAG 检索），会议纪要可发布入库沉淀为团队资料                                                                      |
| 桌面本地执行                                    | SQLite 持久化、Python Sidecar 生命周期与业务 IPC 待接；窗口、应用信息 IPC 和 Web 集成已完成                                                             |
| 部门 / 权限 / Agent / Skill 版本 / 聊天等业务表 | 部分落地：`users` 表 + JWT 认证已实现（docs/api-architecture.md）；Agent 配置含 `department`（专业范畴）/ `sop`（标准流程）/ `skills`（技能绑定）待建表 |

## 技术栈

| 层      | 技术                                                                              |
| ------- | --------------------------------------------------------------------------------- |
| Web     | Vite + React 19 + TanStack Router + Zustand + assistant-ui + BlockNote            |
| 共享 TS | TypeScript 6 + tsup                                                               |
| 服务端  | Python 3.11 + FastAPI + SQLAlchemy 2.x + Alembic（aiosqlite）+ httpx + websockets |
| 数据库  | SQLite（单文件 `services/api/data/dp_work.db`，零依赖）                           |
| 工程化  | pnpm 10 + ESLint 10 + Prettier 3 + Commitlint + Husky                             |

## 目录结构

```
apps/desktop    Electron 桌面客户端（复用 Web 页面）
apps/web        Web 前端（Vite + React + assistant-ui；features 按模块划分）
packages/       共享 TS 包（workspace 内引用）
services/       Python 服务（sidecar：ASR+本地转写；api：SQLite 存储）
docs/           项目文档（转写同步方案 / 架构图）
```

## 子包 / 服务作用

| 包 / 服务             | 目录                  | 作用                                                                                                                                                                                                                                                                                                       |
| --------------------- | --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `@dp-work/contracts`  | `packages/contracts`  | Web ↔ Sidecar 的 camelCase 消息、转写分句及桌面 IPC 类型定义。                                                                                                                                                                                                                                             |
| `@dp-work/api-client` | `packages/api-client` | 浏览器 / Node 通用 **API 客户端**（批量上行分句、健康检查）                                                                                                                                                                                                                                                |
| `@dp-work/ui`         | `packages/ui`         | 两端复用 UI 组件（骨架，待从 `apps/web` 提取）                                                                                                                                                                                                                                                             |
| `@dp-work/tsconfig`   | `packages/tsconfig`   | 共享 TypeScript 配置（`base.json`）                                                                                                                                                                                                                                                                        |
| sidecar               | `services/sidecar`    | 本机 ASR、临时片段文件和 SQLite 确认片段；对接豆包真实识别，云端同步待接入。                                                                                                                                                                                                                               |
| api                   | `services/api`        | **企业级 API 底座**：统一响应 `{code,message,data}`、JWT 认证守卫（登录/刷新、require_role/require_dept）、RequestContext 中间件、全局异常过滤器；SQLite 单文件存储（`users` / `knowledge_bases`）；按业务模块分层；测试与目录说明见 `services/api/README.md`（默认单元/API 测试，集成测试显式指定测试库） |
| web                   | `apps/web`            | Web 前端：Agent 工作台 + 会议模块（features 按模块组织）                                                                                                                                                                                                                                                   |

## 如何启动

按依赖顺序：**api → sidecar → web**（SQLite 单文件，无需任何数据库服务）。

### 1. 初始化数据库

```bash
cd services/api && .venv/bin/python -m alembic upgrade head   # 首次启动建表
```

### 2. api 服务（:8000）

```bash
cd services/api && python -m venv .venv && source .venv/bin/activate && pip install -e .
cp .env.example .env        # 环境变量按子包单独管理，服务启动时自动加载本目录 .env
alembic upgrade head         # 仅适用于空库或已纳入 Alembic 管理的库
uvicorn app.main:app --port 8000
```

依赖和数据库准备完成后，日常可在仓库根目录用 `pnpm dev:api` 启动 API，再用 `pnpm dev:web` 启动前端。

### 3. sidecar（:8001，豆包 ASR）

```bash
cd services/sidecar && python -m venv .venv && source .venv/bin/activate && pip install -e .
cp .env.example .env        # 填写豆包语音服务 API Key
uvicorn src.main:app --host 127.0.0.1 --port 8001
```

### 4. Web 前端（:3000）

```bash
cd apps/web && cp .env.example .env.local   # Next.js 自动加载 .env.local（NEXT_PUBLIC_* 内联）
pnpm install   # 首次
pnpm dev
```

登录/注册请求体使用 JWE 加密密码；本地 HTTPS 启动与证书配置见 [Web README](apps/web/README.md#https-与密码传输)。

打开 http://localhost:3000 → 开始会议 → 输入标题 → 实时转写（mock 分句流）→ 结束会议 → 列表页显示「会议纪要 AI 生成中」。

## 数据存储路径（SQLite 本地层）

实时转写、待同步队列（outbox）、草稿与本地缓存统一保存在应用数据目录：

| 环境                  | 路径                                                                                    |
| --------------------- | --------------------------------------------------------------------------------------- |
| 开发                  | `<项目根>/.dp-work/data/`（已 gitignore，不入库）                                       |
| 生产（Electron 打包） | `app.getPath("userData")/data/`（macOS：`~/Library/Application Support/<App名>/data/`） |

- 开发期 Web 用浏览器 IndexedDB（DB `dp-work-local`）模拟 SQLite，接口按 SQLite 语义设计（saveSegments / pendingSegments / markSynced…），Electron 期换 better-sqlite3 调用方不变。
- 规划库文件：`dp.db`（实时转写）、`outbox.db`（待同步队列）、`drafts.db`（草稿 / 缓存）。

## 工程化工具

| 工具                | 说明                                           |
| ------------------- | ---------------------------------------------- |
| pnpm 10             | 包管理，`apps/*`、`packages/*` 为 workspace    |
| ESLint 10           | 代码检查（eslint-config-next + flat config）   |
| Prettier 3          | 代码格式化（统一全仓风格）                     |
| Commitlint          | 提交信息规范（Conventional Commits）           |
| Husky + lint-staged | 提交前自动 lint / format / 校验 commit message |

## 常用命令

```bash
pnpm install        # 安装依赖（首次）
pnpm dev            # 启动 web 开发服务器
pnpm build          # 构建
pnpm lint           # 全仓 eslint 检查
pnpm lint:fix       # eslint 自动修复
pnpm format         # prettier 检查格式
pnpm format:fix     # prettier 自动格式化
```

## 子包集成

- ESLint（`eslint.config.mjs`）与 Prettier（`.prettierrc.json` / `.prettierignore`）的配置统一收口在仓库根目录，子包**不维护独立配置**。
- 子包内执行 `pnpm lint` / `pnpm format` 时自动向上继承根配置（已实测：`apps/web` 内 lint 0 error、format 全绿）；新增子包无需重复配置。
- 根目录的 `pnpm lint` / `pnpm format` 覆盖全仓（含所有子包），提交前 lint-staged 也会对暂存的子包文件自动执行 eslint --fix 与 prettier --write。

## 提交规范

提交信息遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

```
<type>(<scope>): <subject>

# 示例
feat(web): 添加知识库 @ 选择
fix(chat): 修复消息流中断问题
docs: 更新会议纪要流程说明
chore: 升级依赖
```

- `type`：feat / fix / docs / style / refactor / perf / test / build / ci / chore / revert
- 提交时 pre-commit 自动对暂存文件跑 eslint --fix 与 prettier --write，commit-msg 校验信息格式，不合法会被拦截。

## 说明

- TypeScript 固定使用 6.x（typescript-eslint 尚不支持 TS 7）。
- `eslint.config.mjs` 关闭了 `react-hooks/refs`、`react-hooks/set-state-in-effect`（hooks 6.x 新规则，与模板的 useRef 缓存值 / effect 同步 setState 模式冲突）。

## Electron 桌面端

桌面客户端位于 `apps/desktop`，运行 `pnpm dev:desktop` 可启动并复用 Web 页面；API 仍使用 `pnpm dev:api` 单独启动。构建和打包说明见 [Desktop README](apps/desktop/README.md)。
