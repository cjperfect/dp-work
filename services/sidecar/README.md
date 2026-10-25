# Sidecar

已实现麦克风 PCM 采集、豆包双向流式识别和 Web ↔ Sidecar ASR 协议。临时片段保存到 `.dp-work/temp/asr`，确认片段写入 SQLite 后推送到页面。API 批量同步尚未接入。

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

仅使用豆包真实识别。缺少凭证时明确提示配置错误，不生成示例转写。

## 豆包配置

在本服务 `.env` 中设置，凭证不放进 Web 或 Electron Renderer：

```dotenv
VOLC_API_KEY=你的语音服务API_Key
VOLC_RESOURCE_ID=volc.seedasr.sauc.duration
VOLC_SPEAKER_INFO=1
```

仅支持新版控制台 API Key 鉴权，连接地址固定为 `wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async`。资源 ID 必须与实际开通的 1.0/2.0、小时版/并发版匹配。

修改 `.env` 后重启 Sidecar；修改桌面端权限代码后重启 Electron。页面点击“开始转写”后申请麦克风，准备完成后才连接豆包；暂停/结束先排空麦克风尾帧，再发送结束包并等待最终分句。识别说话人编号不代表真实姓名，暂停后的新识别会话不保证同一人沿用相同编号。

依据[豆包官方双向流式 API](https://docs.volcengine.com/docs/DoubaoVoice/bidirectional-streaming-automatic-speech-recognition-websocket?lang=zh)接入：启用分句、二遍识别和标点；`definite` 仅表示分句确认，整个识别流是否结束由协议帧标志判断。

浏览器通过本机 `/health` 查询服务与凭证是否已填写，再建立 WebSocket。该查询不会返回密钥。Electron 只允许自身主页面申请麦克风，不开放摄像头和屏幕采集。

## 目录

- `src/transport/`：控制消息校验、WebSocket 路由。
- `src/meetings/`：识别会话；`repository.py` 统一管理 SQLite 与临时片段文件。
- `src/providers/asr/`：豆包二进制协议、流式连接。
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

收到 `asr.ready` 后才发送 PCM16 小端音频，建议每帧约 200ms（6400 字节），单帧限制 64000 字节。PCM 音频直接转发给豆包进行识别。

| 事件             | 关键字段                                            | 说明                                   |
| ---------------- | --------------------------------------------------- | -------------------------------------- |
| `asr.ready`      | requestId、meetingId、sessionId                     | 服务准备完成                           |
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

同一分句临时更新与最终确认使用同一个 ID，revision 递增。临时文字不写 SQLite，而是按版本逐行追加到 `.dp-work/temp/asr/<meetingId>/<sessionId>/transcripts.jsonl`，每行是一条 JSON 记录；确认片段成功提交 SQLite 后清理该片段的所有临时版本，保留其他未确认片段，文件为空时删除，异常断开或保存失败时保留；isFinal=true 只能在 SQLite 事务提交后发送。前端按 ID 和版本去重，确认文字不被临时结果覆盖。

`meetings.repository.read_temporary(meeting_id, session_id)` 按片段 ID 选取最大 revision，并按 seq 返回最新临时片段。读取时忽略异常退出留下的不完整尾行，追加和清理前修复尾行；完整记录不会被丢弃。目前提供内部读取方法，尚未接入页面恢复接口。

seq 在会议内持续递增，时间戳相对于有效录音时间轴。新连接从已保存的序号和有效录音时长继续，保留录音中的静音，不包含暂停间隔；sessionId 每次重新生成。片段 ID 包含 sessionId，避免异常重连后临时片段版本冲突。

停止：

```json
{ "type": "asr.stop", "requestId": "stop-001", "meetingId": "meeting-001" }
```

前端停止发送音频后发送 stop。Sidecar 向豆包发送负序号尾帧，等待确认分句保存并推送后，再发送 stopped；前端等待回执后关闭连接，不提前断开丢失尾句。断线前未确认的文字不自动当作确认片段保存。

同步状态预留 pending、syncing、synced、failed。目前云端同步未启用，确认片段保留为 pending；没有待同步数据才返回 synced。stopped 只代表本地完成，不代表 PostgreSQL 已保存。

## 配置与边界

`DP_DATA_DIR` 默认指向仓库根 `.dp-work/data`，SQLite 文件为 `dp.db`；临时目录使用同级的 `.dp-work/temp`；生产运行时由 Electron 传入用户数据目录。该阶段需单独启动 Sidecar，Electron 尚未托管其进程生命周期。

服务默认只监听本机回环地址，浏览器连接只接受 localhost / 127.0.0.1 / ::1 来源。会议权限与用户身份校验将在真实 API 联调时接入；不作为可公开访问的转写服务部署。

`src/asr.py`、`src/store.py`、`src/sync.py` 是此前遗留的实现/占位，当前入口不再调用；新的协议路径以上述 transport → meetings → providers 为准。

## 验证范围

`pnpm test:sidecar` 使用本机伪造的 WebSocket 上游验证真实豆包适配器，包括鉴权头、PCM 帧、尾帧、分句确认、临时文件和 SQLite。不会发送实际麦克风音频或调用付费服务。

前端运行 `pnpm --filter @dp-work/web test:asr`，验证采样率转换、PCM16 字节序、录音取消、权限拒绝和最后一帧处理。实际豆包连通性仍需填入有效凭证后实测。
