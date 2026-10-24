"""SQLite 本地转写存储（一分句一行 + 待同步队列）。

开发期数据目录默认 <项目根>/.dp-work/data；生产 Electron 场景由主进程传入
用户数据目录路径（DP_DATA_DIR）。表结构对齐服务端 transcript_segments，
额外携带同步状态字段（pending/synced + attempt）。
"""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

_DP_DATA_DIR = os.environ.get("DP_DATA_DIR")
DATA_DIR = Path(_DP_DATA_DIR) if _DP_DATA_DIR else Path(__file__).resolve().parents[2] / ".dp-work" / "data"
DB_PATH = DATA_DIR / "dp.db"

_LOCK = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS transcript_segments (
  id          TEXT PRIMARY KEY,          -- 分句 id = 幂等键（meeting_id#seq）
  meeting_id  TEXT NOT NULL,
  seq         INTEGER NOT NULL,
  speaker     TEXT,
  text        TEXT NOT NULL,
  start_ms    INTEGER,
  end_ms      INTEGER,
  sync_status TEXT NOT NULL DEFAULT 'pending',  -- pending / synced
  attempt     INTEGER NOT NULL DEFAULT 0,
  created_at  INTEGER NOT NULL,
  UNIQUE (meeting_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_segments_meeting_seq ON transcript_segments (meeting_id, seq);
CREATE INDEX IF NOT EXISTS idx_segments_sync ON transcript_segments (meeting_id, sync_status);
"""


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _LOCK, _connect() as conn:
        conn.executescript(SCHEMA)


def max_seq(meeting_id: str) -> int:
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), -1) AS m FROM transcript_segments WHERE meeting_id = ?",
            (meeting_id,),
        ).fetchone()
        return int(row["m"])


def save_segments(meeting_id: str, segments: list[dict[str, Any]], start_seq: int) -> int:
    """append-only 追加定型分句；同 id 已存在则跳过（幂等）。"""
    now = int(__import__("time").time() * 1000)
    with _LOCK, _connect() as conn:
        written = 0
        for i, seg in enumerate(segments):
            seq = start_seq + i
            seg_id = f"{meeting_id}#{seq}"
            cur = conn.execute(
                """INSERT OR IGNORE INTO transcript_segments
                   (id, meeting_id, seq, speaker, text, start_ms, end_ms, sync_status, attempt, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?)""",
                (seg_id, meeting_id, seq, seg.get("speaker"), seg.get("text", ""),
                 seg.get("start_ms"), seg.get("end_ms"), now),
            )
            written += cur.rowcount
        conn.commit()
        return written


def pending_segments(meeting_id: str, limit: int = 200) -> list[dict[str, Any]]:
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            """SELECT * FROM transcript_segments
               WHERE meeting_id = ? AND sync_status = 'pending'
               ORDER BY seq ASC LIMIT ?""",
            (meeting_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_synced(meeting_id: str, ids: list[str]) -> int:
    with _LOCK, _connect() as conn:
        if not ids:
            return 0
        cur = conn.execute(
            f"""UPDATE transcript_segments SET sync_status = 'synced'
                WHERE meeting_id = ? AND id IN ({','.join('?' * len(ids))})""",
            (meeting_id, *ids),
        )
        conn.commit()
        return cur.rowcount


def clear_meeting(meeting_id: str) -> int:
    with _LOCK, _connect() as conn:
        cur = conn.execute("DELETE FROM transcript_segments WHERE meeting_id = ?", (meeting_id,))
        conn.commit()
        return cur.rowcount
