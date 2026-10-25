"""SQLite 转写片段与持久化待同步记录。"""
from contextlib import contextmanager
import sqlite3
import threading
import time

from ..config import DATA_DIR

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
