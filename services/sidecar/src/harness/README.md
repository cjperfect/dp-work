# Harness

第一版提供运行事件边界，模型与工具循环继续由 `agents/agent.py` 的 `create_agent` 执行。

- `runtime.py`：统一 API 传入的 `run_id`，发布开始事件、完成或错误终态；终态之后停止转发，并释放底层事件迭代器。
- 执行超时和取消沿用 Agent 的异步执行逻辑；API 断开连接后，Sidecar 关闭模型网络连接。
- PG 中的 `agent_runs`、会话互斥、查询、取消和过期恢复由 API 管理。Sidecar 不重复保存业务记录。
- 本阶段没有审批、Skills 装配、工具管理扩展或检查点恢复。异常中断需要用户重试，不自动续跑。

正式聊天：Web → API 创建运行 → Sidecar Harness → create_agent → SSE → API 提交运行与消息终态 → Web。整个链路沿用同一运行 ID。
