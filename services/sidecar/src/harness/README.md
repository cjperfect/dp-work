# Harness

模型与工具循环由 `agents/agent.py` 的 `create_deep_agent` 执行。

- `runtime.py`：统一 run_id 与事件边界。approval 表示暂停，不当作失败，也不当作完成。
- `approvals.py`：按工具参数判断风险的审批规则，以及按运行隔离的磁盘检查点。检查点提交后才发送审批事件，批准前不执行工具。
- PG 的 agent_runs 管理执行记录、互斥、取消与过期恢复；agent_approvals 管理审批记录与一次性决定。会话消息用 waiting_approval 区分暂停和生成中。
- API 固定原执行设备；恢复时校验用户、运行状态、审批状态和检查点中断 ID。拒绝后把工具拒绝结果返回模型，批准后执行原参数。
- 待审批时结束当前网络请求，不占用持续等待的模型连接。刷新后重新查询 PG 获取卡片，模型运行检查点保留在本机。正常结束清理检查点，断线、设备离线或检查点丢失不会自动重试操作。

链路：Web → API 创建运行 → Electron 设备通道 → Sidecar JSON-RPC → Deep Agents → SSE → API 持久化 → Web。审批恢复沿用相同 run_id 和回复 ID。

普通创建/编辑文件直接执行；敏感路径变更、删除、重定向及无法静态确认的命令经 `tool_policy.py` 判定后审批。`AGENT_MAX_STEPS` 为执行循环预算，图节点上限按 ×6+8 换算，避免中间件节点耗尽普通文件操作的预算。
