"""sidecar 配置：加载本服务目录 .env（变量按子包单独管理）并收口全部变量。

本服务目录：services/sidecar/app/config.py → parents[1]。
本地数据目录默认 = 仓库根目录 .dp-work/data（生产 Electron 由 DP_DATA_DIR 覆盖为用户数据目录）。
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

SERVICE_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(SERVICE_ROOT / ".env")
REPO_ROOT = SERVICE_ROOT.parents[1]

# ---- 本地数据目录（SQLite / 音频缓存）----
# 留空 = 仓库根 .dp-work/data；生产 Electron 传用户数据目录（如 userData）
DP_DATA_DIR = os.environ.get("DP_DATA_DIR", "")
DATA_DIR = Path(DP_DATA_DIR) if DP_DATA_DIR else REPO_ROOT / ".dp-work" / "data"

# ---- 上行同步到 api ----
SYNC_API_BASE = os.environ.get("SYNC_API_BASE", "http://localhost:8000").rstrip("/")
SYNC_INTERVAL_SEC = float(os.environ.get("SYNC_INTERVAL_SEC", "5"))
SYNC_BATCH_SIZE = int(os.environ.get("SYNC_BATCH_SIZE", "200"))

# ---- ASR ----
# 1 = mock 流（开发联调），0 = 接真实豆包流式 ASR（需 VOLC_* 凭证）
MOCK_ASR = os.environ.get("MOCK_ASR", "1") == "1"
VOLC_ACCESSKEY = os.environ.get("VOLC_ACCESSKEY", "")
VOLC_SECRETKEY = os.environ.get("VOLC_SECRETKEY", "")
VOLC_APPID = os.environ.get("VOLC_APPID", "")
VOLC_CLUSTER = os.environ.get("VOLC_CLUSTER", "")

# ---- 服务端口 ----
PORT = int(os.environ.get("PORT", "8001"))
