"""会议转写的 SQLite 存储与临时文件管理。"""
from contextlib import contextmanager
import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
import sqlite3
import threading
import time

from ..config import DATA_DIR, TEMP_DIR

DB_PATH = DATA_DIR / "dp.db"
_LOCK = threading.Lock()


@contextmanager
def connection():
    """打开数据库并在操作完成后关闭连接。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    """初始化转写表。"""
    with _LOCK, connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS transcript_segments (
          id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL, seq INTEGER NOT NULL,
          speaker TEXT, text TEXT NOT NULL, start_ms INTEGER, end_ms INTEGER,
          sync_status TEXT NOT NULL DEFAULT 'pending', attempt INTEGER NOT NULL DEFAULT 0,
          created_at INTEGER NOT NULL, UNIQUE(meeting_id, seq)
        );
        CREATE INDEX IF NOT EXISTS idx_segments_meeting_seq ON transcript_segments(meeting_id, seq);
        CREATE INDEX IF NOT EXISTS idx_segments_sync ON transcript_segments(meeting_id, sync_status);
        CREATE TABLE IF NOT EXISTS asr_recording_sessions (
          session_id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL,
          offset_ms INTEGER NOT NULL, duration_ms INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_recording_sessions_meeting ON asr_recording_sessions(meeting_id);
        """)


def position(meeting_id: str) -> tuple[int, int]:
    """读取下一分句序号与有效录音时间偏移。"""
    with _LOCK, connection() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), -1)+1 AS seq, COALESCE(MAX(end_ms), 0) AS offset "
            "FROM transcript_segments WHERE meeting_id=?", (meeting_id,),
        ).fetchone()
        recording = conn.execute(
            "SELECT COALESCE(MAX(offset_ms+duration_ms),0) FROM asr_recording_sessions WHERE meeting_id=?",
            (meeting_id,),
        ).fetchone()[0]
        return int(row["seq"]), max(int(row["offset"]), int(recording))


def save_segment(meeting_id: str, segment: dict):
    """提交确认片段，重复提交不覆盖已保存的数据。"""
    with _LOCK, connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO transcript_segments "
            "(id,meeting_id,seq,speaker,text,start_ms,end_ms,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (segment["id"], meeting_id, segment["seq"], segment["speakerId"], segment["text"],
             segment["startMs"], segment["endMs"], int(time.time()*1000)),
        )


def pending_count(meeting_id: str) -> int:
    """统计持久化待同步片段。"""
    with _LOCK, connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM transcript_segments WHERE meeting_id=? AND sync_status='pending'",
            (meeting_id,),
        ).fetchone()[0]


def save_duration(meeting_id, session_id, offset_ms, duration_ms):
    """保存有效录音时长，恢复后保留静音间隔但排除暂停时间。"""
    with _LOCK, connection() as conn:
        conn.execute(
            "INSERT INTO asr_recording_sessions(session_id,meeting_id,offset_ms,duration_ms) VALUES (?,?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET duration_ms=MAX(duration_ms,excluded.duration_ms)",
            (session_id, meeting_id, offset_ms, duration_ms),
        )


def segment_path(meeting_id: str, session_id: str, seq: int) -> Path:
    """按会议、识别会话和分句序号定位临时文件。"""
    if any(not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", value) for value in (meeting_id, session_id)):
        raise ValueError("无效的转写目录标识")
    if type(seq) is not int or seq < 0:
        raise ValueError("无效的分句序号")
    target = TEMP_DIR / "asr" / meeting_id / session_id / f"{seq}.json"
    if not target.resolve().is_relative_to(TEMP_DIR.resolve()):
        raise ValueError("临时片段路径超出临时目录")
    return target


def save_temporary(meeting_id: str, session_id: str, segment: dict) -> Path:
    """原子替换临时片段文件，避免中途读取到不完整 JSON。"""
    target = segment_path(meeting_id, session_id, segment["seq"])
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                prefix=".partial-", suffix=".tmp", delete=False) as stream:
            staging = Path(stream.name)
            json.dump(dict(meetingId=meeting_id, sessionId=session_id, segment=segment),
                      stream, ensure_ascii=False)
        os.replace(staging, target)
        return target
    finally:
        if staging:
            staging.unlink(missing_ok=True)


def remove_temporary(meeting_id: str, session_id: str, seq: int):
    """仅清理已经写入 SQLite 的片段及其空会话目录。"""
    target = segment_path(meeting_id, session_id, seq)
    target.unlink(missing_ok=True)
    for directory in (target.parent, target.parent.parent):
        try:
            directory.rmdir()
        except OSError:
            break
