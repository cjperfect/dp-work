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

Electron 复用同一份 `dist`，由桌面 Main 提供静态服务、SPA 路由回退及 API 转发，见 `apps/desktop/README.md`。文档、会议和 Agent 的尚未接入能力继续使用现有本地演示存储。
