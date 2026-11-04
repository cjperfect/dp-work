# Redis 临时状态

Redis 用于 API/模型调用限流、查询 Embedding 缓存和实时通知。业务任务、正文、权限与执行结果仍以 PostgreSQL 为准，RabbitMQ/Celery 继续负责持久化任务。

## 本机启动

```sh
pnpm redis:up
```

Compose 默认绑定 `127.0.0.1:6380`，避免与其他项目占用的 6379 冲突；可以通过 `REDIS_PORT` 修改映射。API 与 Sidecar 的 `.env` 分别配置 `REDIS_URL=redis://127.0.0.1:6380/0`，随后重启 API、Celery Worker 和 Electron/Sidecar。

- API：`REDIS_IP_RPM=600`、`REDIS_USER_RPM=300`；固定窗口从第一次请求开始计算，默认 60 秒。IP 来源是 ASGI peer，不信任任意 `X-Forwarded-For`；网关部署需正确配置 Uvicorn 的可信代理地址，避免所有用户共享网关 IP。
- Sidecar：`REDIS_MODEL_RPM=120`、`REDIS_MODEL_USER_RPM=60`；按服务地址、模型 ID 与凭证摘要区分服务配置，用户身份来自当前执行上下文。Agent 每轮、子 Agent、标题、压缩、纪要及记忆调用都经过实际模型适配器；Embedding 的网络重试也计数。SDK 内部重试属于同一次逻辑聊天调用，不额外计数。这是请求数限额，不是 Token 预算。
- `REDIS_LIMIT_FAIL_OPEN=0`：限流服务故障时 API 返回 503，模型调用返回安全错误；设置 1 可故障放行。限流命中 API 返回 429 与 `Retry-After`。限额为 0 关闭对应规则，Redis URL 留空关闭整个功能。
- `REDIS_CACHE_TTL_SECONDS=300`：只缓存查询向量，不缓存文档向量化结果、检索正文或带工具调用的 Agent 回复。缓存 key 包含用户、完整 Embedding profile、模型服务配置摘要和查询文本摘要；不存原始查询、模型密钥或用户 JWT。命中后仍校验向量，坏缓存与 Redis 故障按未命中处理；每次检索继续通过 PG 校验权限和索引版本。

个人桌面场景下，Sidecar 只能使用本机 Redis 或可访问的可信私网 Redis；不在安装包内嵌入云端 Redis 凭证、不开放公网 Redis。跨机器共享限额需要这些执行进程连接同一受控 Redis；离线桌面未配置 Redis 时没有分布式限流，仅保留原有本机预算控制。生产使用 ACL、私网及 `rediss://`。这不是对恶意桌面客户端不可绕过的云端计费网关。

## 提交后通知与回退

`notifications.notify()` 在业务事务中写 PG NOTIFY，并将同一事件缓冲在 Session 中；`session.transaction()` 正常提交后才发布 Redis Pub/Sub。回滚不发布。消息只携带现有状态标识或协同 awareness，不增加正文和凭证。

订阅端同时保留 PG 与 Redis 通道：优先接收 Redis，PG 延迟 150ms 补发，用随机事件 ID 去重。Redis 断线自动重连，PG 仍可交付。这种兼容实现保留原有 PG 订阅连接，暂不减少数据库连接数；Pub/Sub 本身不保存离线消息，客户端重连后读取数据库最新状态。双通道都中断时，不承诺事件重放或恰好一次送达。

Redis 容器限制为 256MB、`noeviction`，避免内存压力时静默淘汰限流计数；缓存和计数均有 TTL。内存满时缓存写入降级，限流按故障策略处理；需要监控内存并按负载调整，Redis 不启用持久化。

## 验证

普通测试关闭开发 Redis。真实 Redis 测试使用随机前缀和短 TTL，不执行 FLUSHDB；通知测试只在独立频道发送消息，不修改业务表：

```sh
cd services/api
TEST_REDIS_URL=redis://127.0.0.1:6380/0 .venv/bin/python -m pytest tests/redis tests/unit/test_redis_notifications.py -q
# 额外设置 TEST_NOTIFY_DATABASE_URL 可验证真实 PG 提交/回滚通知。
cd ../sidecar
TEST_REDIS_URL=redis://127.0.0.1:6380/0 .venv/bin/python -m pytest tests/providers/test_redis_control.py tests/providers/llm/test_rate_limit.py -q
```

固定窗口限流算法统一使用 `limits.aio` 的 `RedisStorage` 与 `FixedWindowRateLimiter`，不再维护两套自定义 Lua。每次操作使用所属事件循环内的 Redis 连接池，并在完成后关闭；保留 Celery 独立事件循环兼容性。规则维度、凭证指纹、缓存隔离及错误策略由业务适配层维护。升级后使用新的限流 key 格式，已有窗口计数不会迁移，旧 key 按 TTL 自行过期。
