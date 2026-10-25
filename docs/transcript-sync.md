# 转写同步方案（实时落库 + 定时批量上行）

> 状态：已确认方案 · 待接入实现
> 关联：`docs/asr-sync-flow.html`（流程图）、`docs/db-architecture.html`（数据库分工）

## 1. 总体流程

```
豆包流式 ASR（show_utterances: true）
   │ definite=false → 中间结果：实时更新界面当前行（不落库）
   │ definite=true  → 分句定型：写入本地 SQLite（status=pending）
   ▼
SQLite dp.db（本地实时保存）
   │ 每 5s 定时批量取出 pending（≤200 条/批；online 事件立即 flush）
   ▼
后端 API（幂等 upsert，按分句 id）
   ├── 成功 → status=synced
   └── 失败 → 保留 pending，下个周期自动重试
   ▼
SQLite（定稿）
会议结束 → 立即 flush 剩余队列 → 后端仅用定型分句生成纪要
```

## 2. definite 判定（豆包分句自带，无需自研 VAD）

| 值                | 含义       | 前端行为                                                      |
| ----------------- | ---------- | ------------------------------------------------------------- |
| `definite: false` | 中间结果   | 持续更新编辑器当前「待定行」，不落库                          |
| `definite: true`  | 分句已确定 | 定型该行（发言人加粗、时间戳固化）→ 落库 pending → 开新待定行 |

- 流式请求需开启 `show_utterances: true`。
- Sidecar 把 utterance 事件（含 definite）透传给前端，经 Main IPC / JSON-RPC。

## 3. 存储分工

| 存储                     | 职责                                                                                      |
| ------------------------ | ----------------------------------------------------------------------------------------- |
| **SQLite**（本地事实源） | 用户、部门、权限、Agent、Skill 版本、聊天、会议、转写片段（定稿）、纪要、知识库资料元数据 |
| **SQLite**（桌面本地层） | 实时转写（pending）、待同步队列（outbox）、草稿、本地缓存                                 |
| 向量检索（预留）         | 知识库资料 chunk 向量，语义检索（RAG 召回）                                               |

- 数据目录：开发 `<项目根>/.dp-work/data/`；生产 Electron `app.getPath("userData")/data/`（详见 README「数据存储路径」）。
- 主键统一 UUID：离线生成的片段/纪要 id 先落 SQLite，上行后与 Postgres 幂等对应（`idempotency_key` = 分句 id）。

## 4. 同步参数（当前阶段建议值）

| 项       | 建议值                            | 说明                                                                 |
| -------- | --------------------------------- | -------------------------------------------------------------------- |
| 同步间隔 | 5s                                | 定时批量取 pending                                                   |
| 批量大小 | ≤ 200 条/批                       | 一次请求多条分句                                                     |
| 幂等键   | 分句 id（会议 id + utterance id） | 后端按 key upsert，重试不重复                                        |
| 失败处理 | 保留 pending，下周期重试          | 后续可升级指数退避（30s → 2m → 10m，上限 ~5 次后转 failed 人工处理） |
| 网络恢复 | online 事件立即 flush             | 断网重连不丢数据                                                     |
| 会议结束 | 立即 flush + 等结果               | 保证纪要用全量分句                                                   |

## 5. 数据库性能三原则

批量同步的目的正是降低 DB 压力，瓶颈在**事务数、索引更新、锁**而非调用频率：

1. **分句表 append-only**：只 `INSERT` 不 `UPDATE`，仅建 `(meeting_id, seq)` 索引 → 无行锁冲突、无热页更新。
2. **批量单语句写入**：`INSERT INTO transcript_segments (...) VALUES (...), (...) ON CONFLICT (id) DO NOTHING` → 一个事务合并一批，幂等去重在同一语句内。
3. **分句不进向量索引**：向量索引只服务知识库资料（构建昂贵），转写同步不触碰。

量级参考：一场 1 小时会议 ≈ 1500~2000 条分句，5s 一批 ≈ 每批 2~3 条、约 700 余批，对 SQLite 压力很小；高吞吐导入场景（如历史转写批量导入）调大间隔（30s+）与批内条数（50~200）即可。

## 6. 落地清单（待办）

- [ ] 定 Sidecar JSON-RPC 协议：`asr.stream` / `asr.utterance`（含 definite）/ `outbox.flush` / `outbox.poll`
- [ ] Electron Main 建 SQLite（dp.db / outbox）：schema + `getDataDir()` 路径解析
- [ ] 后端批量写入接口：幂等 upsert + 权限校验（上行时服务端强制）
- [x] Postgres 表结构：transcript_segments（append-only）等，统一由 `services/api/migrations`（Alembic）管理，旧库基线快照见 `services/api/tests/fixtures/legacy_schema.sql`
- [ ] 前端：BlockNote 待定行逻辑（definite=false 更新 / definite=true 定型落库）
