# Desktop

Electron 桌面壳，页面复用 `apps/web` 的 Vite + React 应用。

## 开发启动

在根目录运行：

```bash
pnpm dev:api
# 另开终端
pnpm dev:desktop
```

`dev:desktop` 优先复用 `http://localhost:3000` 的 Web 服务；没有服务时自动启动。Web 页面支持热更新，修改 Electron Main 或 Preload 后重新运行 `dev:desktop`。

可复制 `.env.example` 为本目录的 `.env`，修改开发页面地址。桌面应用的 localStorage 与普通浏览器独立，需要分别登录。

## 数据持久化

开发环境使用项目根目录 `.dp-work/`，生产环境使用用户主目录 `~/.dp-work/`：

```text
.dp-work/
  data/          Electron 持久化数据，包括 localStorage、IndexedDB 等
  logs/          应用日志
    crashes/     崩溃文件
  cache/         Chromium 磁盘缓存
```

Token 仍由页面通过 localStorage 保存，文件由 Electron 管理，放在 `data/` 内，不会单独保存为 token 文件。浏览器网页版的站点存储仍由浏览器管理。

首次迁移会复制旧用户数据目录中的浏览器存储，保留原目录；已有新目录数据时不覆盖。迁移前需退出旧版桌面应用。开发与生产环境的数据分开保存，不自动跨环境同步。

## 构建与打包

```bash
pnpm build:desktop                          # 编译桌面入口并生成内置 Web 产物
pnpm --filter @dp-work/desktop preview      # 使用内置 Web 产物预览
pnpm package:desktop:dir                    # 生成未封装成安装包的应用目录
pnpm package:desktop                        # 生成当前平台的安装包
```

Web 构建输出到 `apps/web/dist`，打包时仅复制静态产物及不含密钥的 API 地址配置，不复制 `.env`、Node.js 依赖或开发源码。产物位于 `apps/desktop/release/`。

桌面应用启动后，在 Main 进程启动轻量本地静态服务，支持 SPA 路由回退和 `/api` 转发，默认监听 `127.0.0.1:34731`；退出应用时关闭。固定端口用于保持 localStorage 的来源一致；如果端口被占用会提示启动失败。

FastAPI 仍是独立服务，API 地址默认读取 Web 的 `API_BASE_URL`，也可在桌面构建或运行环境中通过 `DESKTOP_API_BASE_URL` 覆盖。当前不打包 PostgreSQL、FastAPI 或 Python Sidecar。安装包发布所需签名、证书及自动更新后续接入。

## 目录

```text
src/
  main.ts       窗口、IPC 和应用生命周期
  preload.ts    提供给页面的桌面接口
  server.ts     静态资源、路由回退、API 代理和开发服务等待
  config.ts     开发地址和端口校验
scripts/        开发启动、Web 产物准备和生产预览
```

Renderer 启用沙箱和上下文隔离，关闭 Node.js 集成。页面通过 `window.desktop?.getInfo()` 读取桌面信息，类型定义在 `packages/contracts/src/desktop.ts`。IPC 仅允许主窗口的同源主框架调用。
