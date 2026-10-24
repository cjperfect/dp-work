# Web 前端

Next.js 承载页面入口和 `/api/chat`；浏览器内的页面导航由 TanStack Router 文件路由负责。
路由组织参考 [shadcn-admin](https://github.com/satnaing/shadcn-admin/tree/main/src/routes)。

## 路由目录

```text
router.tsx                         # 创建 Router、注册类型、导出 AppRouter
routeTree.gen.ts                   # 自动生成并提交，禁止手动修改
routes/
├── __root.tsx                     # 根 Outlet、404
└── _app/
    ├── route.tsx                  # 登录校验与无路径公共布局
    ├── index.tsx                  # /
    ├── product.tsx                # /product
    ├── meetings/
    │   ├── index.tsx              # /meetings
    │   ├── active.tsx             # /meetings/active
    │   └── minutes.tsx            # /meetings/minutes
    ├── skills/index.tsx           # /skills
    ├── connectors/index.tsx       # /connectors
    └── knowledge/
        ├── index.tsx              # /knowledge
        └── $kbId/
            ├── index.tsx          # /knowledge/$kbId
            └── files/$fileId.tsx  # /knowledge/$kbId/files/$fileId
components/layout/app-shell.tsx    # 公共侧边栏、聊天 Runtime、面包屑
features/                          # 业务页面与逻辑
```

`_app` 是 pathless layout，不会出现在 URL 中。路由文件保持轻量，只定义路径、
`staticData.title` 等路由信息，并通过 `lazyRouteComponent` 加载业务页面。
公共布局不会因子路由导航而卸载；页面自身的状态仍由对应业务模块管理。
`routes/(auth)/sign-in.tsx` 与 `sign-up.tsx` 是独立于工作区布局的登录、注册页。

## 开发

在仓库根目录安装依赖后，执行：

```bash
pnpm dev
```

启动时先生成路由树，再并行启动路由文件监听与 Next.js。
新增、删除、重命名路由会自动更新 `routeTree.gen.ts`，无需维护集中式路由列表。
Next.js 当前使用 Turbopack，因此这里通过独立 CLI 生成路由树，而不是 Vite 插件。

也可单独执行：

```bash
pnpm --filter @dp-work/web routes:generate
pnpm --filter @dp-work/web routes:watch
pnpm --filter @dp-work/web typecheck
pnpm --filter @dp-work/web build
```

构建和类型检查前都会重新生成路由树。`routeTree.gen.ts` 已从 ESLint、Prettier 检查中排除。
`app/[[...path]]/page.tsx` 仍是 Next.js 的客户端入口，水合后挂载 `AppRouter`。

## 新增页面

1. 在 `features/<模块>` 实现业务页面。
2. 在 `routes/_app/<模块>` 新建路由，导出 `Route = createFileRoute(...)({...})`。
3. 配置 `staticData.title`，公共布局会读取它作为面包屑标题。
4. 动态参数使用带 `from` 的 `useParams` 获取，导航使用 `Link` / `useNavigate`。
5. 提交路由文件及重新生成的 `routeTree.gen.ts`。

## 登录与注册

- `/sign-in`：用户名、密码登录。
- `/sign-up`：用户名、密码注册；用户名 2–32 字符且不含空格，密码 8–128 字符。
- 注册账号默认是普通成员，部门为 `unassigned`，不能通过注册参数指定角色或部门。
- 未登录访问工作区会跳到登录页，登录/注册后回到原始站内地址。
- JWT 仅保存在当前标签页的 sessionStorage；刷新后通过 `/auth/users/me` 验证身份。
- 侧边栏底部显示当前用户并提供退出登录。

先启动 `services/api`（以及其 PostgreSQL），再启动 Web。Web 通过 Next.js rewrite 将
`/api/v1/*` 转发至企业 API，默认地址 `http://127.0.0.1:8000`。
可在 Web 的 `.env.local` 设置 `API_BASE_URL`，修改后重启 Web。

认证接口：`POST /api/v1/auth/login`、`POST /api/v1/auth/register`，请求均为
`{ "username": "…", "password": "…" }`。成功返回统一响应中的 `{ token, user }`。
前端路由守卫负责页面访问体验；数据权限仍由服务端认证和部门/角色守卫执行。
