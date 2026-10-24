# dp-work

企业 Agent 平台 monorepo。

## 结构

```
apps/web        Web 前端（Next.js 16 + React 19 + assistant-ui）
packages/       共享 TS 包（workspace 内引用）
docs/           项目文档
infra/          基础设施（docker-compose、PG 初始化脚本）
services/       Python 服务（sidecar：ASR+本地转写；api：Postgres 写入）
```

## 共享包（packages/）

| 包                    | 内容                                                                       |
| --------------------- | -------------------------------------------------------------------------- |
| `@dp-work/contracts`  | IPC、JSON-RPC、事件的协议定义（WS 消息 / 转写分句 / 上行批量的类型与常量） |
| `@dp-work/api-client` | 桌面端与 Web 共用的 TS API 客户端（批量上行分句、健康检查）                |
| `@dp-work/ui`         | 两端有复用需求的 UI 组件（骨架，待从 apps/web 提取）                       |
| `@dp-work/tsconfig`   | 共享 TypeScript 配置（`base.json`）                                        |

## 基础设施

```bash
docker compose up -d   # 启动 PostgreSQL（含 pgvector 扩展），端口 5432
```

- PostgreSQL（`pgvector/pgvector:pg16`）：服务端事实源 + 知识库语义检索向量库。
- 首次启动自动执行 `infra/postgres/init/` 下的初始化脚本（启用 vector 扩展）。

## 服务（services/）

| 服务    | 目录               | 职责                                                                                      |
| ------- | ------------------ | ----------------------------------------------------------------------------------------- |
| sidecar | `services/sidecar` | 豆包流式 ASR + 本地 SQLite 实时转写保存（一分句一行）+ 待同步队列（outbox）+ 定时批量上行 |
| api     | `services/api`     | FastAPI：接收批量上行，幂等写入 PostgreSQL `transcript_segments`                          |

```bash
# api（需先 docker compose up -d 启动 PG）
cd services/api && python -m venv .venv && source .venv/bin/activate && pip install -e .
export DATABASE_URL="postgresql://dp:dp_dev_password@localhost:5432/dp_work"
uvicorn app.main:app --port 8000

# sidecar
cd services/sidecar && python -m venv .venv && source .venv/bin/activate && pip install -e .[asr]
export DP_DATA_DIR="$(cd ../.. && pwd)/.dp-work/data"   # 生产 Electron 传用户数据目录
uvicorn app.main:app --port 8001
```

- Sidecar 每 5s 取本地 pending 分句批量上行（`SYNC_INTERVAL_SEC` / `SYNC_BATCH_SIZE` 可调），失败保留 pending 下周期重试；会议结束触发立即 flush。
- 豆包 ASR 接入需安装 `volcengine-python-sdk[streaming]` 并配置 `VOLC_ACCESSKEY / VOLC_SECRETKEY / VOLC_APPID / VOLC_CLUSTER`，见 `services/sidecar/README.md`。

## 数据存储路径（SQLite 本地层）

实时转写、待同步队列（outbox）、草稿与本地缓存统一保存在应用数据目录：

| 环境                  | 路径                                                                                    |
| --------------------- | --------------------------------------------------------------------------------------- |
| 开发                  | `<项目根>/.dp-work/data/`（已 gitignore，不入库）                                       |
| 生产（Electron 打包） | `app.getPath("userData")/data/`（macOS：`~/Library/Application Support/<App名>/data/`） |

- 路径解析由 Electron 主进程 `getDataDir()` 统一负责（`app.isPackaged` 判断环境），Renderer 经 IPC 获取，不直接拼路径。
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
