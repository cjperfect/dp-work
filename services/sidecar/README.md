# Sidecar

已实现麦克风 PCM 采集、豆包双向流式识别和 Web ↔ Sidecar ASR 协议。未确认片段保存到 `.dp-work/temp/asr` 的 JSONL。确认片段推送到页面，前端立即请求 API 保存到 PostgreSQL；Sidecar 不创建或读写 SQLite，不维护待同步队列。

## 启动

```bash
cd services/sidecar
python -m venv .venv
source .venv/bin/activate
pip install -e ../../packages/agent-templates -e .
cp .env.example .env
uvicorn src.main:app --reload --host 127.0.0.1 --port 8001
```

已有虚拟环境时，可以在仓库根目录运行 `pnpm dev:sidecar`。测试：`pnpm test:sidecar`。

仅使用豆包真实识别。缺少凭证时明确提示配置错误，不生成示例转写。

## 豆包配置

在本服务 `.env` 中设置，凭证不放进 Web 或 Electron Renderer：

```dotenv
VOLC_API_KEY=你的语音服务API_Key
VOLC_BASE_URL=wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async
VOLC_RESOURCE_ID=volc.seedasr.sauc.duration
VOLC_SPEAKER_INFO=1
```

仅支持新版控制台 API Key 鉴权，连接地址由 `VOLC_BASE_URL` 配置，默认 `wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async`，填写完整 WebSocket 地址。资源 ID 必须与实际开通的 1.0/2.0、小时版/并发版匹配。

修改 `.env` 后重启 Sidecar；修改桌面端权限代码后重启 Electron。进入进行中的会议并取得编辑权限后自动申请麦克风，准备完成后才连接豆包；暂停/结束先排空麦克风尾帧，再发送结束包并等待最终分句。识别说话人编号不代表真实姓名，暂停后的新识别会话不保证同一人沿用相同编号。

依据[豆包官方双向流式 API](https://docs.volcengine.com/docs/DoubaoVoice/bidirectional-streaming-automatic-speech-recognition-websocket?lang=zh)接入：启用分句、二遍识别和标点；`definite` 仅表示分句确认，整个识别流是否结束由协议帧标志判断。

浏览器通过本机 `/health` 查询服务与凭证是否已填写，再建立 WebSocket。暂停会议不会自动录音，恢复会议后自动重启转写；启动失败可点击“重试转写”。该查询不会返回密钥。Electron 只允许自身主页面申请麦克风，不开放摄像头和屏幕采集。

## 目录

- `src/transport/`：控制消息校验、WebSocket 路由。
- `src/meetings/`：识别会话；`repository.py` 仅管理未确认片段的 JSONL 临时文件。
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
  "nextSeq": 0,
  "offsetMs": 0,
  "audio": { "format": "pcm", "sampleRate": 16000, "channels": 1, "bitsPerSample": 16 }
}
```

收到 `asr.ready` 后才发送 PCM16 小端音频，建议每帧约 200ms（6400 字节），单帧限制 64000 字节。PCM 音频直接转发给豆包进行识别。

| 事件             | 关键字段                                            | 说明                                   |
| ---------------- | --------------------------------------------------- | -------------------------------------- |
| `asr.ready`      | requestId、meetingId、sessionId                     | 服务准备完成                           |
| `asr.transcript` | meetingId、sessionId、segment                       | 临时文字或识别已确认的片段             |
| `asr.stopped`    | requestId、meetingId、sessionId、lastFinalSeq       | 最后的确认片段已推送                   |
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

同一分句临时更新与最终确认使用同一个 ID，revision 递增。临时文字按版本逐行追加到 `.dp-work/temp/asr/<meetingId>/<sessionId>/transcripts.jsonl`，每行是一条 JSON 记录；确认片段成功推送后清理该片段的所有临时版本，保留其他未确认片段，文件为空时删除，异常断开或推送失败时保留；isFinal=true 只表示识别确认，不代表 API 已保存。前端按 ID 和版本去重，确认文字不被临时结果覆盖。

`meetings.repository.read_temporary(meeting_id, session_id)` 按片段 ID 选取最大 revision，并按 seq 返回最新临时片段。读取时忽略异常退出留下的不完整尾行，追加和清理前修复尾行；完整记录不会被丢弃。目前提供内部读取方法，尚未接入页面恢复接口。

seq 在会议内持续递增，时间戳相对于有效录音时间轴。新连接由前端从 API 读取会议状态和转写记录，携带 nextSeq（下一序号）与 offsetMs（会议有效时间偏移）继续，保留录音中的静音，不包含暂停间隔；sessionId 每次重新生成。片段 ID 包含 sessionId，避免异常重连后临时片段版本冲突。

停止：

```json
{ "type": "asr.stop", "requestId": "stop-001", "meetingId": "meeting-001" }
```

前端停止发送音频后发送 stop。Sidecar 向豆包发送负序号尾帧，等待确认分句推送后，再发送 stopped；前端等待回执后关闭连接，不提前断开丢失尾句。断线前未确认的文字不自动当作确认片段保存。

保存反馈以 API 返回为准，前端等待每条确认片段保存完成后才处理 stopped；API 失败会显示保存错误并停止本次转写，当前页面保留未保存内容供重试。没有 SQLite 持久化队列，刷新或异常退出前仍未成功保存的确认片段可能丢失。

## 配置与边界

`DP_DATA_DIR` 仅用于确定同级 `temp` 目录，留空使用服务器仓库 `.dp-work/temp`。旧 `.dp-work/data/dp.db` 不再使用；原文件不自动删除。

服务默认只监听本机回环地址，浏览器连接只接受 localhost / 127.0.0.1 / ::1 来源。会议权限与用户身份校验将在真实 API 联调时接入；不作为可公开访问的转写服务部署。

此前遗留的 SQLite 存储、旧 ASR 实现和批量同步文件已经删除，当前链路为 transport → meetings → providers。

## 验证范围

`pnpm test:sidecar` 使用本机伪造的 WebSocket 上游验证真实豆包适配器，包括鉴权头、PCM 帧、尾帧、分句确认、临时文件和 SQLite。不会发送实际麦克风音频或调用付费服务。

前端运行 `pnpm --filter @dp-work/web test:asr`，验证采样率转换、PCM16 字节序、录音取消、权限拒绝和最后一帧处理。实际豆包连通性仍需填入有效凭证后实测。

## 会议纪要提示词

首版系统提示词位于 `src/meetings/prompts/minutes.md`，约定版本为 `minutes-v1`。模型调用已接入，使用前需配置方舟 API Key。

调用时另行传入会议标题、时间、时区及带片段 ID、相对时间和说话人的转写内容。任务 ID、原始内容版本、实际模型和提示词版本由服务记录，不让模型填写。

## 火山方舟会议纪要

模型调用已接入方舟 Chat Completions，参照[方舟 Base URL 与鉴权文档](https://console.volcengine.com/ark/region%3Acn-beijing/docs/base-url-and-authentication)。

在 `services/sidecar/.env` 填写：

```dotenv
ARK_API_KEY=你的方舟APIKey
ARK_MODEL=deepseek-v4-1-flash-261017
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

`ARK_API_KEY` 独立于 ASR 的 `VOLC_API_KEY`。修改配置后重启 Sidecar。实际模型访问权限和效果需配置有效 Key 后验证，接入测试不调用付费模型。

API 通过设备通道将 `meetings.minutes.generate` 任务交给 Electron，再以 stdin/stdout JSON-RPC 调用本机 Sidecar。Sidecar 不提供业务 HTTP 接口。`SIDECAR_INTERNAL_TOKEN` 仍用于 Sidecar 向 API 的知识库检索回调，不是本机 HTTP 入口凭证。

Sidecar 读取 `minutes-v1` 系统提示词，按片段顺序整理标题、会议时间、说话人和原始内容。结果以完整 Markdown 返回，并带实际模型、提示词版本、任务 ID 和原始内容版本。截断、空结果和缺少约定章节的结果不会作为成功纪要保存。

默认单次调用总超时 180 秒，输出上限 8192 tokens，输入字符上限 120000，可通过 `.env.example` 中的配置调整。超长会议当前明确报错，不静默截断，也未加入分段摘要。这里不自动重试模型请求。

## 桌面子进程模式

Electron 使用 `desktop_entry.py --stdio`（安装版 `dp-work-sidecar --stdio`）启动 Sidecar。普通业务通过 stdin/stdout JSON-RPC，日志写 stderr；ASR 音频仍使用本机 WebSocket。网络服务只保留健康检查与 ASR WebSocket，不注册 `/internal`；普通业务通过方法名直接分发到 `transport/handlers.py` 的处理函数，票据与 ASR 共用会话状态。

跨语言声明集中在 [packages/protocols](../../packages/protocols/README.md)：TS 导入编译后的类型/常量，Python 读取同一份 `protocol.json`。业务请求只使用 JSON-RPC；单独运行 Uvicorn 仅能提供健康检查和 ASR WebSocket。

## 开发评测

LangSmith 离线评测入口：在仓库根目录执行 `pnpm eval:smoke` 检查链路，`pnpm eval:live` 使用真实模型。默认不上传，只有显式 `--upload` 才提交合成数据与实验。安装、评分与数据边界见 [evals/README.md](evals/README.md)。
