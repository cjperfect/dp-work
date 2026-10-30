"""sidecar 配置：加载本服务目录 .env（变量按子包单独管理）并收口全部变量。

本服务目录：services/sidecar/src/config.py → parents[1]。
未确认片段临时目录默认使用仓库 .dp-work/temp。
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

SERVICE_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(os.environ.get("DP_SIDECAR_ENV_FILE") or SERVICE_ROOT / ".env")
REPO_ROOT = SERVICE_ROOT.parents[1]

# ---- 未确认片段的临时目录 ----
DP_DATA_DIR = os.environ.get("DP_DATA_DIR", "")
DATA_ROOT = Path(DP_DATA_DIR).parent if DP_DATA_DIR else REPO_ROOT / ".dp-work"
TEMP_DIR = DATA_ROOT / "temp"
# 各 Agent 默认工具的本机工作目录，与 Electron 使用相同位置。
WORKSPACE_DIR = DATA_ROOT / "workspace"

# ---- ASR ----
VOLC_BASE_URL = os.environ.get("VOLC_BASE_URL", "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async").strip()
VOLC_API_KEY = os.environ.get("VOLC_API_KEY", "").strip()
VOLC_RESOURCE_ID = os.environ.get("VOLC_RESOURCE_ID", "volc.seedasr.sauc.duration")
VOLC_SPEAKER_INFO = os.environ.get("VOLC_SPEAKER_INFO", "1") == "1"

# ---- 服务端口 ----
PORT = int(os.environ.get("PORT", "8001"))

# ---- 方舟大模型（Agent 与会议纪要共用） ----
ARK_API_KEY = os.environ.get("ARK_API_KEY", "").strip()
ARK_MODEL = os.environ.get("ARK_MODEL", "").strip()
ARK_BASE_URL = os.environ.get("ARK_BASE_URL", "").rstrip("/")
ARK_TIMEOUT_SECONDS = float(os.environ.get("ARK_TIMEOUT_SECONDS", "180"))
ARK_MAX_TOKENS = int(os.environ.get("ARK_MAX_TOKENS", "8192"))
MINUTES_MAX_INPUT_CHARS = int(os.environ.get("MINUTES_MAX_INPUT_CHARS", "120000"))
SIDECAR_INTERNAL_TOKEN = os.environ.get("SIDECAR_INTERNAL_TOKEN", "").strip()

# ---- PDF 文档解析 ----
PDF_PARSE_TIMEOUT = float(os.environ.get("PDF_PARSE_TIMEOUT", "90"))

# ---- Agent 执行限制 ----
AGENT_MAX_STEPS = int(os.environ.get("AGENT_MAX_STEPS", "12"))
# 相同工具、参数、结果的连续重复次数；达到后阻止下一次相同调用。
AGENT_REPEAT_LIMIT = max(1, int(os.environ.get("AGENT_REPEAT_LIMIT", "3")))
# 连续明确标记为 error 的工具结果上限；达到后不再执行新工具。
AGENT_TOOL_ERROR_LIMIT = max(1, int(os.environ.get("AGENT_TOOL_ERROR_LIMIT", "5")))
# Windows Linux 容器沙箱只接受本机已构建镜像的不可变 sha256 ID，不自动拉取。
AGENT_SANDBOX_IMAGE = os.environ.get("AGENT_SANDBOX_IMAGE", "").strip()
# 每个运行的预算；0 表示不设限制，达到已报告用量后阻止下一次模型调用。
AGENT_RUN_TOKEN_LIMIT = max(0, int(os.environ.get("AGENT_RUN_TOKEN_LIMIT", "0")))
AGENT_RUN_COST_LIMIT = os.environ.get("AGENT_RUN_COST_LIMIT", "0")
# 所有配置单价使用同一币种，按每百万 Token 计价；不内置供应商价格。
AGENT_COST_CURRENCY = os.environ.get("AGENT_COST_CURRENCY", "CNY").upper()
AGENT_MODEL_PRICES = os.environ.get("AGENT_MODEL_PRICES", "{}")

# ---- 本机长期记忆后台生成 ----
MEMORY_AUTO_ENABLED = os.environ.get("MEMORY_AUTO_ENABLED", "1") == "1"
MEMORY_IDLE_HOURS = max(0.01, float(os.environ.get("MEMORY_IDLE_HOURS", "6")))
MEMORY_SCAN_SECONDS = max(10, float(os.environ.get("MEMORY_SCAN_SECONDS", "60")))
MEMORY_MAX_AGE_DAYS = max(1, min(90, int(os.environ.get("MEMORY_MAX_AGE_DAYS", "30"))))
MEMORY_BATCH_SIZE = max(1, min(16, int(os.environ.get("MEMORY_BATCH_SIZE", "4"))))
MEMORY_EXTRACT_MODEL = os.environ.get("MEMORY_EXTRACT_MODEL", "").strip()
MEMORY_CONSOLIDATION_MODEL = os.environ.get("MEMORY_CONSOLIDATION_MODEL", "").strip()

# ---- 知识库文本向量化（与聊天模型配置分开） ----
EMBEDDING_API_KEY = os.environ.get("EMBEDDING_API_KEY", "").strip()
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "doubao-embedding-vision-251215").strip()
EMBEDDING_BASE_URL = os.environ.get("EMBEDDING_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
EMBEDDING_DIMENSIONS = int(os.environ.get("EMBEDDING_DIMENSIONS", "1024"))
EMBEDDING_TIMEOUT_SECONDS = float(os.environ.get("EMBEDDING_TIMEOUT_SECONDS", "30"))
# API 内部检索回调地址；只由服务端环境指定，不接受浏览器提交。
API_INTERNAL_URL = os.environ.get("API_INTERNAL_URL", "http://127.0.0.1:8000").rstrip("/")

# 长期记忆语义检索的最低余弦相似度及单轮超时（秒）。
MEMORY_MIN_SIMILARITY = max(-1.0, min(1.0, float(os.environ.get("MEMORY_MIN_SIMILARITY", "0.25"))))
MEMORY_RETRIEVAL_TIMEOUT_SECONDS = max(1, float(os.environ.get("MEMORY_RETRIEVAL_TIMEOUT_SECONDS", "10")))

# ASR 每小时音频估算单价（与 AGENT_COST_CURRENCY 同币种）；留空不估算费用。
ASR_PRICE_PER_HOUR = os.environ.get("ASR_PRICE_PER_HOUR", "").strip()
