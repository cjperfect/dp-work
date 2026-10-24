-- PostgreSQL 初始化脚本（docker-entrypoint-initdb.d，首次启动自动执行）

-- 启用 pgvector 扩展，供知识库语义检索使用
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- 转写分句表（append-only：只 INSERT 不 UPDATE）
-- 一条 definite=true 分句 = 一行
-- id = 幂等键，采用 "<meetingId>#<seq>" 文本格式（与前端 outbox 一致，
--     天然跨会话重放幂等）；meeting_id 当前为会议标识（后续接 meetings
--     实体表后再统一为 uuid，此处先保证链路可跑通）
-- ============================================================
CREATE TABLE IF NOT EXISTS transcript_segments (
  id          text PRIMARY KEY,            -- 幂等键 "<meetingId>#<seq>"
  meeting_id  text NOT NULL,               -- 所属会议标识
  seq         int  NOT NULL,               -- 会议内序号（渲染/纪要排序）
  speaker     text,                        -- 发言人
  text        text NOT NULL,               -- definite=true 定型文本
  start_ms    int,                         -- 相对会议开始偏移
  end_ms      int,
  status      smallint NOT NULL DEFAULT 0, -- 0 定稿 / 1 人工修订
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (meeting_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_transcript_segments_meeting
  ON transcript_segments (meeting_id, seq);

-- ============================================================
-- 会议纪要表（定稿后写入，支持协同编辑）
-- ============================================================
CREATE TABLE IF NOT EXISTS minutes (
  id          text PRIMARY KEY,            -- 幂等键 "<meetingId>-minutes"
  meeting_id  text NOT NULL,
  title       text NOT NULL,
  content     text NOT NULL DEFAULT '',    -- 纪要正文（结构化 JSON 或 Markdown）
  status      smallint NOT NULL DEFAULT 0, -- 0 生成中 / 1 已生成 / 2 已发布到知识库
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (meeting_id)
);

-- ============================================================
-- 用户表（认证体系，docs/api-architecture.md §4.1）
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
  id            text PRIMARY KEY,            -- 幂等键，如 "u-<username>"
  username      text NOT NULL UNIQUE,        -- 登录名（邮箱或工号）
  password_hash text NOT NULL,               -- pbkdf2_sha256$iterations$salt$hash
  display_name  text NOT NULL,
  department    text NOT NULL,               -- 部门标识（专业范畴的载体）
  role          text NOT NULL DEFAULT 'member',  -- admin / manager / member
  status        smallint NOT NULL DEFAULT 0, -- 0 正常 / 1 停用
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- ============================================================
-- 知识库资料文本分块向量表（pgvector 语义检索）
-- 向量维度按实际 embedding 模型配置（如 OpenAI text-embedding-3-large = 3072）
-- ============================================================
-- CREATE TABLE IF NOT EXISTS knowledge_chunks (
--   id          uuid PRIMARY KEY,
--   asset_id    uuid NOT NULL,             -- 关联知识库资料
--   chunk_index int  NOT NULL,             -- 分块序号
--   content     text NOT NULL,             -- 分块文本
--   embedding   vector(1536),
--   created_at  timestamptz NOT NULL DEFAULT now()
-- );
-- CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding
--   ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);
