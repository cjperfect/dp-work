# 个人设置已迁至本地

云端不再注册 `/api/settings`；前端同名业务调用由 Axios 本地适配器经 Electron IPC 直接进入 Sidecar，不经过 API 或 PG 设备任务缓存。

`services/sidecar/src/providers/local_settings.py` 按账号保存 `.dp-work/config/users/<user-id>/services.json` 和 `services.key`。API Key 使用 Fernet 加密，目录权限 0700、文件权限 0600，原子写入；本机密钥文件不是操作系统钥匙串，备份配置需一同保存它。

读取只返回 has_api_key；不提交密钥表示保留；更换服务商不能复用原密钥；测试表单不会自动保存。模型、标题、会议纪要与 ASR 由 Sidecar 内存中读取个人配置，关闭个人配置后使用本机环境变量默认值。

会议 ASR 票据改为 `POST /api/meetings/{id}/asr/session`，远程只验证会议归属；API Key 由本机读取。PG 设置表由迁移 0023 删除。
