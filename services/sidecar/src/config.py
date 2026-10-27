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
TEMP_DIR = (Path(DP_DATA_DIR).parent if DP_DATA_DIR else REPO_ROOT / ".dp-work") / "temp"

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

# ---- 知识库文本向量化（与聊天模型配置分开） ----
EMBEDDING_API_KEY = os.environ.get("EMBEDDING_API_KEY", "").strip()
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "doubao-embedding-vision-251215").strip()
EMBEDDING_BASE_URL = os.environ.get("EMBEDDING_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
EMBEDDING_DIMENSIONS = int(os.environ.get("EMBEDDING_DIMENSIONS", "1024"))
EMBEDDING_TIMEOUT_SECONDS = float(os.environ.get("EMBEDDING_TIMEOUT_SECONDS", "30"))
# API 内部检索回调地址；只由服务端环境指定，不接受浏览器提交。
API_INTERNAL_URL = os.environ.get("API_INTERNAL_URL", "http://127.0.0.1:8000").rstrip("/")
