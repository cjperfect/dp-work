# Web

使用 Vite + React + TanStack Router，界面组件包括 assistant-ui、shadcn 和 BlockNote。

## 启动与检查

在项目根目录运行：

```bash
pnpm dev:api
pnpm dev:web
pnpm --filter @dp-work/web typecheck
pnpm --filter @dp-work/web build
```

默认开发地址为 `http://localhost:3000`，API 服务默认位于 `http://127.0.0.1:8000`。复制 `.env.example` 为 `.env.local` 可以修改代理目标。Vite 的 `/api` 代理用于开发、本地预览；正式 Web 部署需要配置反向代理。

`pnpm --filter @dp-work/web start` 仅预览 `dist` 构建产物，不作为生产服务。

## 源码目录

```text
src/
  main.tsx            React 入口与全局 Provider
  router.tsx          TanStack Router 装配
  globals.css         全局样式
  routes/             轻量路由入口
  routeTree.gen.ts    自动生成，不手动修改
  features/           按业务模块组织组件、Hook 和业务工具
  components/         通用组件、shadcn、共享富文本编辑器
  hooks/              通用 Hook
  lib/                HTTP 请求、Token 读取与通用工具
  stores/             按模块组织全部 Store，例如 auth.ts、knowledge.ts
  apis/               按模块组织 API 请求，例如 auth.ts、knowledge.ts
  types/              业务类型
  constants/          通用常量
  interfaces/         跨模块的类型
```

业务 Hook 放在所属 feature 的 `hooks/` 下，跨模块使用时从该 feature 引入。页面路由直接导入，关闭路由自动拆分；富文本编辑器、PDF 等重型组件仍通过 React.lazy 和 Suspense 按需加载。路由由 TanStack Router Vite 插件自动生成。

## API 与登录

认证、知识库接口通过 `src/lib/http.ts` 的 Axios 客户端统一处理响应、超时和 Authorization。Token 保存在 localStorage，有效期由后端控制。用户信息直接缓存登录接口的返回值，应用启动时从本地恢复一次，页面路由不拦截登录状态，不请求当前用户接口；业务接口收到 401 时清理登录状态并跳转登录页，旧请求不会清除新会话。

前端只请求 `/api/...`。浏览器正式部署可配置：

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000;
}
location / {
    try_files $uri $uri/ /index.html;
}
```

Electron 复用同一份 `dist`，由桌面 Main 提供静态服务、SPA 路由回退及 API 转发，见 `apps/desktop/README.md`。会议、知识库和账号使用远程 API；Agent、会话、技能、连接器、项目和用量通过统一 Axios 本机适配器转为 Electron IPC，不回退到演示数据。

## 代码组织

- `routes/`：路由声明与页面入口，不编写业务请求。
- `features/<module>/`：页面、业务组件、Hook 和纯逻辑。页面负责布局，Hook 负责请求编排、取消及交互状态；复用的业务状态仍放 Store。
- `apis/`：请求函数、SSE 读取和响应转换；统一使用 `lib/http.ts`，不在页面、Hook 或 Store 中直接 fetch/axios。外部图片读取使用独立客户端，避免附带业务 Token。
- `interfaces/`：按模块集中维护业务模型、接口请求与响应类型，不从 API 或常量文件导入业务类型。组件内部 Props 和局部辅助类型可就近声明。
- `constants/`：按模块集中维护内置目录、展示映射和固定配置，不放业务接口类型、请求或状态。
- `stores/`：按业务模块存放共享状态与动作；`hooks/` 放通用 Hook，业务 Hook 留在相应 feature。

知识库请求保留 `apis/knowledge.ts` 统一入口，实现拆为 `knowledge/client.ts`（账号及请求校验）、`mappers.ts`（响应转换）、`bases.ts`、`documents.ts`、`files.ts`、`processing.ts`。旧在线文档迁移独立在 `document-migration.ts`，不与常规文档 CRUD 混写。

工具展示入口为 `components/assistant-ui/elements/tool-fallback.aui.tsx`。`tool-approval/model.ts` 负责审批状态与标签计算，`receipt.tsx` 展示已处理结果，`questions.tsx` 展示多问题输入，`index.tsx` 编排审批操作与焦点。原有公共组件接口保持不变。

技能页面通过 `use-skills` 读取已安装列表，`use-skill-market` 管理防抖搜索与简介补齐，`use-skill-actions` 管理上传、安装、卸载与变更后的刷新。连接器页面通过 `use-connector-page` 编排授权操作。

Agent Store 的 `state.ts` 只维护共享状态和基础状态操作；`index.ts` 是对外入口。内部动作模块直接引用 `state.ts` 或其他具体动作模块，不从入口反向导入自身。输入草稿由 `agent-message-queue.ts` 本地保存，生成状态由 `state.sending` 管理，两者不再混在旧 drafts 对象中。

## HTTP 调用

`lib/http.ts` 提供 `http.get/post/put/patch/delete`，返回已解包的业务数据。GET 查询参数放 `options.params`，POST/PUT/PATCH 正文作为第二个参数，超时、signal、headers 等放第三个参数。统一拦截器、本机 IPC 适配和登录失效处理继续复用。

```ts
http.get<Result>("/api/example", { params: { page: 1 } });
http.post<Result>("/api/example", data, { timeout: 30000 });
http.patch<Result>("/api/example/1", data);
http.delete<void>("/api/example/1");
```
