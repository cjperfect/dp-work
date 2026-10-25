"""未确认转写片段的临时文件存储。"""
import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile

from ..config import TEMP_DIR


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
