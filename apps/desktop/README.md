# Desktop

Electron 桌面壳，页面复用 `apps/web` 的 Vite + React 应用。

目标部署方式：Web 静态产物、Electron 与 Python Sidecar 安装在用户本机，API 与业务数据库部署在云端。Electron 管理本机 Sidecar 的生命周期。

当前仍连接本机 API `http://127.0.0.1:8000` 验证完整流程，已经采用设备主动连接模式。后续部署云端时，替换公开 API 地址并配置 HTTPS / WSS 网关即可。

云端 API 使用 `SIDECAR_TRANSPORT=device`；Electron Main 在登录后主动建立 WSS 任务连接，通过 stdin/stdout JSON-RPC 交给本机 Sidecar。API 不需要访问用户电脑端口，具体部署见 [设备通道说明](../../services/api/src/modules/devices/README.md)。

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
  workspace/     Agent 独立工作目录
    general/     通用 Agent
    product/     产品 Agent
  data/          Electron 持久化数据，包括 localStorage、IndexedDB 等
  logs/          应用日志
    crashes/     崩溃文件
  cache/         Chromium 磁盘缓存
  temp/          未确认的 ASR 临时片段
```

Agent 加载后通过受限 IPC 创建对应工作目录，目录名使用稳定的 Agent code，修改显示名称不会更换目录；重复启动不会覆盖目录内文件。浏览器网页版不创建本机文件夹。

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

FastAPI 仍是独立服务，API 地址默认读取 Web 的 `API_BASE_URL`，也可在桌面构建或运行环境中通过 `DESKTOP_API_BASE_URL` 覆盖。业务数据由 API 保存到 PostgreSQL。安装包包含独立 Python / Sidecar 运行环境，不包含云端 FastAPI。安装包发布所需签名、证书及自动更新后续接入。

## 目录

```text
src/
  main/
    index.ts                 应用启动与退出编排
    window.ts                主窗口、导航和媒体权限
    ipc.ts                   桌面 IPC 注册与来源校验
    config.ts                页面/API 地址与端口校验
    sidecar/
      config.ts              子进程运行配置
      manager.ts             生命周期、健康检查和重启
      rpc.ts                 stdin/stdout JSON-RPC 客户端
    device/
      bridge.ts              登录设备与 API 的出站连接
    storage/
      persistence.ts         本地目录、旧数据迁移和 Agent 工作目录
    web/
      server.ts              静态服务、SPA 回退和 API 代理
  preload/
    index.ts                 向页面暴露受限桌面接口
scripts/                     开发启动、Web 与 Sidecar 打包
```

编译入口为 `dist/main/index.js`，Preload 为 `dist/preload/index.js`。开发启动、预览和安装包均通过 package.json 的 main 指向主入口。

Renderer 启用沙箱和上下文隔离，关闭 Node.js 集成。页面通过 `window.desktop?.getInfo()` 读取桌面信息，类型定义在 `packages/protocols/src/desktop.ts`。IPC 仅允许主窗口的同源主框架调用。

会议转写需要在 Sidecar `.env` 配置豆包语音凭证。桌面端只允许当前应用主页面访问麦克风；macOS 包已配置麦克风用途说明与录音 entitlement，系统授权由用户确认。

## Sidecar 生命周期

开发环境运行 `pnpm dev:desktop` 时，Main 默认启动 `services/sidecar/.venv` 的 Python，通过 `desktop_entry.py --stdio` 启动管道服务，并在 `127.0.0.1:8001` 保留 ASR WebSocket；不使用 `--reload`，进程由 Main 统一管理。等待健康检查通过后才打开窗口。API 和 MQ Worker 仍需单独启动。

- stdio 模式必须由 Electron 启动子进程，不能复用手动启动的 HTTP Sidecar；ASR 端口被占用时提示关闭手动服务，不终止其他进程。
- 通过 `system.health` RPC 检查服务标识和实例 ID，确认 ASR WebSocket 也已就绪。
- 每 5 秒检查健康；连续 3 次失败或进程异常退出触发重启。重启采用指数退避，60 秒内最多重启 5 次，超过后停止并提示。
- 正常退出先终止自己创建的进程树，POSIX 最多等待 5 秒后强制清理；Windows 使用 `taskkill /T /F`。停止期间不会重新拉起进程。
- Sidecar 仅在托管模式监测父进程，Electron 被强制结束后请求自身退出。手动启动不启用此监测。
- 日志保存在开发根目录或用户目录的 `.dp-work/logs/sidecar.log`，不向界面转发完整日志。

配置位于 `apps/desktop/.env`，字段说明见 `.env.example`。`DESKTOP_SIDECAR_ENABLED=0` 可临时关闭托管。更换本机端口后，应同步修改 Web 的 ASR 连接地址；普通 RPC 不使用监听端口。

安装版默认托管 `resources/sidecar/dp-work-sidecar`（Windows 为 `.exe`），程序与 Python 依赖通过 PyInstaller onedir 一起打包。安装后不需要系统 Python 或开发虚拟环境。可用 `DESKTOP_SIDECAR_EXECUTABLE` 覆盖运行程序；`DESKTOP_SIDECAR_ENABLED=0` 仅用于诊断停用。

## 构建本地 Sidecar

在 `services/sidecar` 安装 `.venv/bin/python -m pip install -e '.[packaging]'`，再运行根目录 `pnpm --filter @dp-work/desktop build:sidecar`。`package` / `package:dir` 自动执行此步骤，输出 `apps/desktop/build/sidecar`，仅复制指定的程序、依赖和提示词资源，不复制 `.env`。

PyInstaller 需在目标操作系统和架构上原生构建；本次验证 macOS arm64。签名与公证仍使用发布者自己的证书配置。模型服务凭证不内置，个人配置可通过云端设置传给当前用户的设备；本机默认配置读取 `~/.dp-work/config/sidecar.env`。

构建安装包前设置 `DESKTOP_API_BASE_URL=https://你的API域名`；该地址是公开配置，会写入 Web 配置文件，并用于 Main 的 WSS 连接和 Sidecar 的检索回调地址。登录后 Main 自动连接，登出后断开，不在安装包内写入账号 Token 或云端密钥。

## 本机业务通信

Main 通过 Sidecar 子进程的 stdin 发送 JSON-RPC 2.0 请求，stdout 接收分行 JSON 消息，stderr 写入 sidecar.log。支持并发请求、流式通知、取消、超时及进程退出时中断在途调用；重启不自动重放。普通业务通过语义方法名直接分发到业务处理函数，没有本机 HTTP 请求或 ASGI 路由适配。

方法和消息定义集中在 [packages/protocols](../../packages/protocols/README.md)。ASR 保留独立 WebSocket 音频通道，桌面 stdio 模式不开放网络 `/internal` 业务接口。API ↔ Main 的出站 WebSocket 设备通道保持原有方式。
