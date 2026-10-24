# Sidecar：豆包流式 ASR + 本地转写实时保存 + 待同步队列

**职责**：接收前端转写命令 → 驱动豆包流式 ASR → 将 definite=true 的分句实时写入本地 SQLite（`dp.db`，一分句一行，status=pending）→ 定时批量上行到 `api` 服务（Postgres 定稿）。

## 启动

```bash
cd services/sidecar
python -m venv .venv && source .venv/bin/activate
pip install -e .
# 本地数据目录（默认 <项目根>/.dp-work/data，生产 Electron 传用户目录路径）
export DP_DATA_DIR="$(cd ../.. && pwd)/.dp-work/data"
# 豆包 ASR 凭证
export VOLC_ACCESSKEY=... VOLC_SECRETKEY=... VOLC_APPID=... VOLC_CLUSTER=volcengine_streaming_common
uvicorn app.main:app --port 8001
```

API 地址默认 `http://localhost:8000`，可用 `SYNC_API_BASE` 覆盖。

## 前端接入

WebSocket `ws://localhost:8001/ws`，JSON-RPC 风格消息：

| 方向   | 消息                                                                                           | 说明                      |
| ------ | ---------------------------------------------------------------------------------------------- | ------------------------- |
| 前端 → | `{"type":"asr.start","meeting_id":"...","sample_rate":16000}`                                  | 开始流式转写              |
| 前端 → | `{"type":"audio","payload":"<base64 pcm>"}`                                                    | 音频数据（Web 录音源）    |
| 前端 → | `{"type":"asr.stop","meeting_id":"..."}`                                                       | 结束（先 flush 上行队列） |
| 后端 → | `{"type":"utterance","definite":false,"text":"...","speaker":"..."}`                           | 中间结果，前端更新当前行  |
| 后端 → | `{"type":"utterance","definite":true,"seq":42,"text":"...","speaker":"...","start_ms":128000}` | 定型分句，已写本地库      |

**注意**：本仓库开发阶段未接 Web 音频采集，可直接用 `app/asr.py` 的麦克风/音频文件入口测试；`definite` 判定依赖豆包 SDK 的 `show_utterances: true`。

## 配置

| 环境变量            | 默认                     | 说明                                 |
| ------------------- | ------------------------ | ------------------------------------ |
| `DP_DATA_DIR`       | `<项目根>/.dp-work/data` | SQLite 数据目录（`dp.db` 放这里）    |
| `SYNC_API_BASE`     | `http://localhost:8000`  | api 服务地址                         |
| `SYNC_INTERVAL_SEC` | `5`                      | 批量上行间隔                         |
| `SYNC_BATCH_SIZE`   | `200`                    | 每批最大分句数                       |
| `VOLC_*`            | -                        | 豆包 ASR 凭证（AK/SK/AppID/Cluster） |
