# API：转写片段定稿写入（PostgreSQL）

**职责**：接收 Sidecar 批量上行，将 definite=true 分句以**单事务多行 INSERT + ON CONFLICT DO NOTHING** 写入 PostgreSQL `transcript_segments`（一分句一行、append-only、幂等）。表结构见 `infra/postgres/init/01-init.sql`。

## 启动

```bash
cd services/api
python -m venv .venv && source .venv/bin/activate
pip install -e .
# 数据库连接（对齐根目录 docker-compose.yml）
export DATABASE_URL="postgresql://dp:dp_dev_password@localhost:5432/dp_work"
uvicorn app.main:app --port 8000
```

依赖 PG 已启动：`docker compose up -d`。

## 接口

### `POST /api/v1/segments` 批量写入（幂等）

```json
{
  "meeting_id": "9f2c...",
  "segments": [
    {
      "id": "9f2c...#42",
      "seq": 42,
      "speaker": "王明",
      "text": "对齐 RAG 召回优化方案",
      "start_ms": 128000,
      "end_ms": 131500
    }
  ]
}
```

返回：`{"written": 1, "ignored": 0}` —— 同 id 重复上行被忽略（不重复计数）。

### `GET /health`

数据库连通性检查。
