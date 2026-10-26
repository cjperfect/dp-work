# dp-work · 企业 Agent 平台

> 把每一场会议都变成企业知识资产，让 Agent 成为团队提效的日常工作伙伴。

dp-work 是一套**企业智能工作台**：会议智能转写与纪要协作、企业知识库沉淀、以及受部门业务规范约束的企业 Agent，三者形成闭环——**会议沉淀知识 → 知识喂养 Agent → Agent 反哺业务**。

---

## 背景

企业中大量的会议内容（讨论过程、关键决策、待办事项）散落在个人笔记与聊天记录里，随会议结束而流失；知识库里的文档长期停留在"存储"层面，难以被检索、引用和复用；通用 AI 助手又缺乏对部门业务范畴与作业流程的约束，输出往往"正确但不可用"。

dp-work 从三个环节解决这个问题：

1. **会议的终点是知识**：实时转写 + AI 生成纪要，让会议重点、决策点、待办事项结构化沉淀；经同事协同确认后归档进知识库，成为可检索、可复用的企业资产。
2. **知识库的终点是能力**：文档经过解析、清洗、分块、向量化，形成 Agent 可以检索引用的知识体系，而不只是一堆文件。
3. **Agent 的终点是业务**：Agent 按部门业务范畴和 SOP 组织能力（Skill），输出受规范约束；通过连接器（如飞书 CLI）直接进入日常办公流。

这样一套下来，每一次会议都能转变为企业知识资产，Agent 也能在规范的边界内真正提高工作效率。

---

## 核心功能

### 1. 智能会议：实时转写 → AI 纪要 → 协同归档

- **会议纪要实时转写**：会议过程中语音实时转写，边开边记；
- **AI 生成会议纪要**：基于转写内容自动生成会议纪要，并以**思维导图**直观展示会议重点、决策点、待办事项；
- **协同编写**：通过分享链接邀请同事一起查看、补充、调整纪要，多人实时协作；
- **归档沉淀**：纪要确认后一键归档到 RAG 知识库，成为企业可检索的知识资产。

### 2. 企业知识库：解析清洗 → 分块向量化 → 可被 Agent 使用

- **多格式支持**：上传 Markdown、PDF、Word、TXT 等常见格式文档；
- **解析与清洗**：自动解析文档内容、清洗格式噪音；
- **分块与向量化**：对文档智能分块（chunk）并向量化存储；
- **形成知识体系**：建立一套 Agent 可以检索引用的企业知识体系，让"文档"变成"能力"。

### 3. 企业 Agent：部门规范约束 + Skill 扩展 + 连接器对接

- **部门业务范畴与 SOP**：将部门职责边界和标准作业流程整理为 **Skill**，Agent 输出内容严格符合部门业务规范，不越界、不跑偏；
- **Skill 可安装**：用户可按需安装 Skill 来扩展 Agent 能力；
- **连接器适配**：可适配连接器（例如飞书 CLI），通过 Agent 对话直接对接飞书等办公系统，把 AI 能力嵌入日常协作。

---

## 技术栈

| 层         | 技术                                                                                                    |
| ---------- | ------------------------------------------------------------------------------------------------------- |
| 前端       | React 19 · TypeScript · Vite · TanStack Router · Tailwind CSS · shadcn/ui · zustand                     |
| 聊天与编辑 | assistant-ui（对话界面）· BlockNote（富文本编辑器，基于 Tiptap）· React Flow（思维导图）                |
| 协同编辑   | Yjs（CRDT 实时协同）· WebSocket（多人协作通道）                                                         |
| 后端 API   | Python · FastAPI · SQLAlchemy · Alembic · PostgreSQL                                                    |
| 实时服务   | WebSocket（ASR 实时转写与状态推送）· Sidecar 服务                                                       |
| AI 能力    | 豆包 ASR（实时语音转写）· 火山方舟大模型（会议纪要生成 / Agent 对话）· 火山方舟向量模型（知识库向量化） |
| 桌面端     | Electron（可选）                                                                                        |
| 工程化     | pnpm monorepo（apps · packages · services）· ESLint · Prettier · Husky                                  |

---

## 启动方式

### 前置依赖

- Node.js ≥ 20、pnpm
- Python 3.11+ 与 uv（后端 API 依赖管理）

### 1. 安装依赖

```bash
pnpm install

# 后端 Python 环境（一次性，后端 API 使用 uv）
cd services/api
uv sync

# AI 引擎端（一次性，sidecar 使用 uv）
cd ../sidecar
uv sync
```

### 2. 配置环境变量

```bash
# 后端环境变量（一次性，按需修改数据库连接、模型 Key 等）
cp services/api/.env.example services/api/.env

# Sidecar 环境变量（一次性，按需修改 ASR / 模型 Key 等）
cp services/sidecar/.env.example services/sidecar/.env
```

### 3. 初始化数据库

```bash
# 启动 PostgreSQL（首次或未运行时）
pnpm db:up

# Alembic 自动建表（PostgreSQL）
pnpm migrate
```

### 4. 启动后端服务

```bash
# API 服务（:8000）
pnpm dev:api

# Sidecar 服务（:8001，ASR 转写 / 模型代理，可选）
pnpm dev:sidecar
```

### 5. 启动前端

```bash
# Web 端（http://localhost:3000）
pnpm dev:web
```

### 6. 启动桌面端（可选）

```bash
pnpm dev:desktop   # Electron 客户端
```

> 日常开发推荐：终端 1 跑 `pnpm dev:api`，终端 2 跑 `pnpm dev:sidecar`，终端 3 跑 `pnpm dev:web`，浏览器打开 `http://localhost:3000`。

---

## 目录结构

```
dp-work/
├── apps/
│   ├── web/          # Web 前端（Vite + React）
│   └── desktop/      # Electron 桌面端（可选）
├── packages/         # 共享包（contracts / api-client / ui 等）
├── services/
│   ├── api/          # 后端 API（FastAPI + PostgreSQL）
│   └── sidecar/      # 实时转写与模型代理服务
└── docs/             # 架构与设计文档
```
