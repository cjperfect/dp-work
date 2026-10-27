# 异步任务

RabbitMQ + Celery 执行会议纪要、解析、向量化、ES 同步。PG 继续保存任务状态、版本、正文及结果，不需要 Redis 或 Celery Result Backend。

## 启动

```sh
# 仓库根目录
pnpm mq:up
pnpm migrate
pnpm dev:api
pnpm dev:sidecar
# 另一个终端，启动四组独立 Celery Worker
pnpm dev:workers
```

配置在 `services/api/.env`；属性注释见 `.env.example`。macOS 默认按并发数启动多组独立 solo Worker，Linux 默认 prefork；可通过 `MQ_WORKER_POOL` 指定。solo 关闭 AMQP 心跳，避免长任务阻塞主线程时被误判离线；任务仍有 asyncio 总超时和 PG 租约恢复。prefork 另外提供进程硬超时。

| 类型     | 队列               | 默认并发 | 配置                   |
| -------- | ------------------ | -------- | ---------------------- |
| 会议纪要 | meeting-minutes    | 2        | MQ_MINUTES_CONCURRENCY |
| 文档解析 | document-parse     | 2        | MQ_PARSE_CONCURRENCY   |
| 向量化   | document-vectorize | 2        | MQ_VECTOR_CONCURRENCY  |
| ES 同步  | search-sync        | 1        | MQ_SEARCH_CONCURRENCY  |

生产环境可按队列独立启动/扩容（在 `services/api` 中运行）：

```sh
.venv/bin/python -m celery -A src.infrastructure.tasks.celery_app:celery_app worker -Q meeting-minutes -c 2 -n minutes@%h --loglevel=INFO
```

并发数是**每个 Worker 实例**的配置，多实例总并发为各实例之和；模型接口的全局配额需据此分配。

## 职责和可靠性

- `models.py` / `outbox.py`：业务数据和消息同事务提交。`kind + target_id + version` 唯一，消息只有 Outbox ID，无正文或凭证。
- `celery_app.py`：四条持久化队列、JSON 序列化、持久化消息、发布确认、执行后 ACK、进程异常退出重投及低预取。
- `src/task_dispatcher.py`：API 只投递消息，Broker 网络调用在独立线程中执行；MQ 故障退避重试，消息保留在 PG。
- `src/task_handlers.py`：业务组合入口，定向领取当前版本；已完成/已删除/旧版本直接跳过。不在消费进程启动 API 生命周期。
- 每次消费使用独立事件循环和数据库连接池并在结束后关闭，避免多进程与 asyncio 跨循环连接复用。
- PG 版本、租约和行锁是幂等边界；无需假设 MQ 恰好投递一次。未完成消息按 `MQ_REDELIVERY_SECONDS` 补投，忙碌/暂时失败的消费稍后重投，不占用 Worker 等待。
- 业务已失败会保存错误并推送前端，用户可以重新提交；数据库异常、Worker 中断、投递失败由持久化消息和租约恢复。ES 临时故障保留同步请求并自动重试。
- 旧 PG 队列中的待执行任务自动生成 Outbox 消息。API 内原来的耗时扫描执行器已移除，只保留消息投递和 ES 索引重建检查。
- PG NOTIFY → API WebSocket → 前端全局 Toast；页面切换继续订阅，任务去重，自动关闭，无关闭图标、查看按钮。ES 只通知当前向量版本索引就绪，删除/清理不提示。

## 部署

RabbitMQ 管理界面：<http://localhost:15672>，本地开发账号/密码 `chenjiang`。Compose 仅绑定回环地址；生产使用专用账号、VHost、访问控制及 TLS。消费者确认超时配置为 2 小时，若增大 `MQ_TASK_TIME_LIMIT` 也需相应调整 RabbitMQ。

API 和 Worker 必须连接相同 PG、RabbitMQ、Sidecar、ES，并共享内部服务凭证、凭证解密密钥。解析 Worker 需要读取上传的源文件：同机共享 `.dp-work/data`；跨主机需共享文件存储后再扩容，不能只复制代码。前端不直接连接 MQ。

`task_outbox.completed_at` 表示该消息已处理或失效，业务是否成功以业务表状态为准。完成记录暂保留用于排查，后续可按保留期清理。
