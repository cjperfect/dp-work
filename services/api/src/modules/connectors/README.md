# 飞书 CLI 连接器

## 已实现

- 官方 `@larksuite/cli` 固定版本 `1.0.98`，项目内安装，暂不接入 Agent。
- 读取安装、应用配置、用户登录状态；主动调用飞书验证 Token。
- 用户通过官方网页或二维码自行完成应用配置和 OAuth 授权。
- 授权流程可取消、超时重试；关闭 API 时回收 CLI 子进程。
- 本机退出登录保留应用配置，不代表撤销飞书服务端的全部授权。

## 本地运行

仓库根目录执行 `pnpm install`、`pnpm setup:feishu-cli`，启动 Web 和 API。
打开连接器页面，依次选择“配置飞书应用”“授权登录”“验证连接”。
应用配置可能需要飞书租户管理员审批，取决于租户策略。

API 只管理 CLI 授权进程；文档、消息等业务命令和 Agent 工具暂未接入。
本次 OAuth 只请求 `auth:user.id:read offline_access`，不申请全域业务权限。

## 存储

- 开发默认配置目录：`.dp-work/connectors/feishu/<平台用户ID>/`。
- `DP_DATA_DIR` 指定数据目录时，连接器目录位于其同级 `connectors/`。
- 使用官方 `LARKSUITE_CLI_CONFIG_DIR` 隔离各平台账号。
- macOS / Linux 下，通过独立 CLI HOME 与 `LARKSUITE_CLI_DATA_DIR` 将凭证密文保存在每个用户的 `credentials/` 子目录。macOS 的加密主密钥继续保存在系统钥匙串，不执行 keychain 降级。
- 首次使用新目录时仅复制当前配置引用的旧应用和用户凭证密文，不复制其他平台账号的凭证；迁移标记防止本机退出后再次导入旧 Token。
- `connection.json` 仅保存应用/用户绑定、账号名称与最近验证时间，不包含明文 Token。
- 后续打开读取已有 CLI 凭证，匹配同一账号时恢复验证记录；短期 Token 待刷新时自动调用 CLI 校验刷新。过期或撤销的授权不通过本地记录伪造为已连接。
- Windows 官方 CLI 的凭证后端仍是 DPAPI 注册表，当前仅配置和验证记录可归入 `.dp-work`，尚未实现 Windows 凭证文件后端。
- 二维码在 `.dp-work/temp/connectors/feishu/` 内临时生成，读取后清理。
- 浏览器不保存应用密钥、设备密钥和 Token，仅展示当前用户的待授权链接和二维码。
- 授权进程重启后不会恢复待完成链接，用户可重新发起；已经完成的登录由 CLI 持久保存。
- 打包部署可通过 `FEISHU_CLI_BIN` 指向已分发的官方原生二进制。

## 接口

均需要平台登录，成功返回 200，使用统一 `{code, message, data}` 响应。

- `GET /api/connectors/feishu`：安装、配置、登录和待授权状态。
- `POST /api/connectors/feishu/authorization/configure`：发起官方应用配置。
- `POST /api/connectors/feishu/authorization/login`：发起用户 OAuth 授权。
- `DELETE /api/connectors/feishu/authorization`：取消当前用户的待授权流程。
- `POST /api/connectors/feishu/verify`：向飞书验证当前登录。
- `POST /api/connectors/feishu/disconnect`：断开本机用户登录。

CLI 仅执行后端定义的固定参数数组，不向前端开放任意命令执行。
