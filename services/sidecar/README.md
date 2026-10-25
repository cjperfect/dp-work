# Sidecar

当前实现 Web ↔ Sidecar ASR 协议与模拟识别流。确认片段写入 SQLite 后才推送到页面；豆包真实识别、麦克风采集、API 批量同步尚未接入。

## 启动

```bash
cd services/sidecar
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
uvicorn src.main:app --reload --host 127.0.0.1 --port 8001
```

已有虚拟环境时，可以在仓库根目录运行 `pnpm dev:sidecar`。测试：`pnpm test:sidecar`。

默认 `MOCK_ASR=1`。当前设为 `0` 会返回 `PROVIDER_NOT_READY`，不会假装识别成功或静默丢弃音频。

## 目录

- `src/transport/`：控制消息校验、WebSocket 路由。
- `src/meetings/`：识别会话、SQLite 转写保存。
- `src/providers/asr/`：模拟识别提供方，后续增加豆包适配。
- 其他 Agent、工具、执行框架目录已预留。

## WebSocket 协议

地址：`ws://localhost:8001/ws`。一条连接只处理一场会议的一次转写会话，暂停后恢复使用新连接。控制与事件用 camelCase JSON，音频使用独立二进制帧。

开始：

```json
{
  "type": "asr.start",
  "requestId": "start-001",
  "meetingId": "meeting-001",
  "audio": { "format": "pcm", "sampleRate": 16000, "channels": 1, "bitsPerSample": 16 }
}
```

收到 `asr.ready` 后才发送 PCM16 小端音频，建议每帧约 200ms（6400 字节），单帧限制 64000 字节。当前模拟提供方只验证音频传输，不对输入内容进行识别。

| 事件             | 关键字段                                            | 说明                                   |
| ---------------- | --------------------------------------------------- | -------------------------------------- |
| `asr.ready`      | requestId、meetingId、sessionId、mode               | 服务准备完成；当前 mode 为 mock        |
| `asr.transcript` | meetingId、sessionId、segment                       | 临时文字或已保存的确认片段             |
| `asr.sync`       | meetingId、pendingCount、status                     | SQLite 待同步状态                      |
| `asr.stopped`    | requestId、meetingId、sessionId、lastFinalSeq       | 最后的确认片段已保存并推送             |
| `asr.error`      | code、message、retryable；可选 requestId、meetingId | 可展示的错误，不包含密钥或上游原始响应 |

转写示例：

```json
{
  "type": "asr.transcript",
  "meetingId": "meeting-001",
  "sessionId": "session-001",
  "segment": {
    "id": "meeting-001#0",
    "seq": 0,
    "revision": 2,
    "text": "今天讨论知识库设计。",
    "speakerId": "speaker-1",
    "startMs": 0,
    "endMs": 1600,
    "isFinal": true
  }
}
```

同一分句临时更新与最终确认使用同一个 ID，revision 递增。临时文字不写 SQLite，而是原子保存到 `.dp-work/temp/asr/<meetingId>/<sessionId>/<seq>.json`；确认片段成功提交 SQLite 后清理对应临时文件，异常断开或保存失败时保留；isFinal=true 只能在 SQLite 事务提交后发送。前端按 ID 和版本去重，确认文字不被临时结果覆盖。

seq 在会议内持续递增，时间戳相对于有效录音时间轴。新连接从已保存片段的序号与结束时间继续，不包含暂停间隔；sessionId 每次重新生成。

停止：

```json
{ "type": "asr.stop", "requestId": "stop-001", "meetingId": "meeting-001" }
```

前端停止发送音频后发送 stop。Sidecar 等待模拟识别当前已展示的文字确认、保存并推送后，再发送 stopped；前端等待回执后关闭连接，不提前断开丢失尾句。断线前未确认的文字不自动当作确认片段保存。

同步状态预留 pending、syncing、synced、failed。目前云端同步未启用，确认片段保留为 pending；没有待同步数据才返回 synced。stopped 只代表本地完成，不代表 PostgreSQL 已保存。

## 配置与边界

`DP_DATA_DIR` 默认指向仓库根 `.dp-work/data`，SQLite 文件为 `dp.db`；临时目录使用同级的 `.dp-work/temp`；生产运行时由 Electron 传入用户数据目录。该阶段需单独启动 Sidecar，Electron 尚未托管其进程生命周期。

服务默认只监听本机回环地址，浏览器连接只接受 localhost / 127.0.0.1 / ::1 来源。会议权限与用户身份校验将在真实 API 联调时接入；不作为可公开访问的转写服务部署。

`src/asr.py`、`src/mock.py`、`src/store.py`、`src/sync.py` 是此前遗留的实现/占位，当前入口不再调用；新的协议路径以上述 transport → meetings → providers 为准。
