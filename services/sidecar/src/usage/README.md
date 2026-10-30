# 本机用量总账

设置页“用量统计”按当前账号汇总 Agent、标题、自动记忆、会议纪要、Embedding 与 ASR。通过本机 `usage.summary` RPC 读取，不发送云端；SQLite 保存到 `.dp-work/data/users/<owner>/usage.sqlite3`，只保存调用标识、能力、模型、关联任务、时间与数值，不保存正文或密钥。从接入后开始累计，不回填此前消耗。

Agent 与标题使用 LangChain 已报告用量；自动记忆与纪要读取 Chat Completions 的 usage；Embedding 按每次真实 HTTP 尝试记录供应商 usage。失败或取消且未返回 usage 时明确记为未报告，不按字符推算 Token。流式事件、审批恢复和 ASR 累计快照按调用 ID 去重；重新生成、应用层重试是新调用，独立计数。

ASR 记录成功发送的 PCM16/16kHz/单声道字节数，除以32000得到音频秒数，每5秒保存部分进度，结束时提交最终快照。它是本机观测值，不等于服务商确认的计费时长；崩溃可能损失最近5秒，之前部分记录保留并标记未完整报告。

费用使用记录当时 `AGENT_MODEL_PRICES` 的每百万 Token 单价及 `AGENT_COST_CURRENCY`。Embedding 只有总 Token 时按 input 单价估算。ASR 使用可选的 `ASR_PRICE_PER_HOUR`。缺少单价、完整用量或调用未结束时费用未知，前端显示已知部分和未知调用数；修改配置不重算旧记录，不同币种分组展示。供应商折扣、套餐及未报告的内部重试不作推测，以服务商账单为准。

统一总账用于观测，现有单任务预算仍只约束 Agent 模型调用，不是账号账单硬上限；不包含外部付费工具和飞书的订阅费用。
