# 飞书连接器已迁至本地

CLI 适配、授权流程、二维码、连接验证和退出逻辑位于 `services/sidecar/src/connectors/`，经 Electron IPC → stdio RPC 调用。云端不再公开 `/api/connectors`。

凭证目录沿用 `.dp-work/connectors/feishu/<user-id>/`，开发环境既有授权可继续使用。执行时只传递固定 CLI 命令，凭证不回传前端或云端，授权进程在 Sidecar 退出时清理。

飞书授权仍需访问飞书服务；技能市场、模型供应商等同样通过本机直接访问对应服务，这与使用项目的远程 API 是不同的通信路径。
