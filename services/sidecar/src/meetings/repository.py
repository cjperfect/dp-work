"""未确认转写的 JSONL 临时文件管理。"""
import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
import threading
from ..config import TEMP_DIR

_LOCK = threading.Lock()


def temporary_path(meeting_id: str, session_id: str) -> Path:
    """定位会议转写会话的 JSONL 临时文件。"""
    if any(not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", value) for value in (meeting_id, session_id)):
        raise ValueError("无效的转写目录标识")
    target = TEMP_DIR / "asr" / meeting_id / session_id / "transcripts.jsonl"
    if not target.resolve().is_relative_to(TEMP_DIR.resolve()):
        raise ValueError("临时片段路径超出临时目录")
    return target


def _repair_temporary_tail(stream) -> None:
    """追加前修复异常退出留下的不完整尾行。"""
    stream.seek(0, os.SEEK_END)
    end = stream.tell()
    if not end:
        return
    stream.seek(end - 1)
    if stream.read(1) == b"\n":
        return
    cursor = end
    tail = b""
    while cursor:
        size = min(cursor, 4096)
        cursor -= size
        stream.seek(cursor)
        tail = stream.read(size) + tail
        boundary = tail.rfind(b"\n")
        if boundary >= 0:
            cursor += boundary + 1
            tail = tail[boundary + 1:]
            break
    try:
        json.loads(tail)
    except (ValueError, UnicodeDecodeError):
        stream.truncate(cursor)
    else:
        stream.seek(0, os.SEEK_END)
        stream.write(b"\n")
    stream.seek(0, os.SEEK_END)


def read_temporary(meeting_id: str, session_id: str) -> list[dict]:
    """读取各片段的最新临时版本，忽略未写完的尾行。"""
    target = temporary_path(meeting_id, session_id)
    segments = {}
    with _LOCK:
        if not target.exists():
            return []
        with target.open("rb") as stream:
            for line in stream:
                try:
                    record = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    if not line.endswith(b"\n"):
                        break
                    raise
                segment = record["segment"]
                previous = segments.get(segment["id"])
                if previous is None or segment["revision"] > previous["revision"]:
                    segments[segment["id"]] = segment
    return sorted(segments.values(), key=lambda segment: segment["seq"])


def save_temporary(meeting_id: str, session_id: str, segment: dict) -> Path:
    """追加一行临时片段版本，写入失败时回退本次追加。"""
    if type(segment["seq"]) is not int or segment["seq"] < 0:
        raise ValueError("无效的分句序号")
    target = temporary_path(meeting_id, session_id)
    line = (json.dumps(dict(meetingId=meeting_id, sessionId=session_id, segment=segment),
                       ensure_ascii=False) + "\n").encode("utf-8")
    with _LOCK:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with target.open("a+b") as stream:
            _repair_temporary_tail(stream)
            position = stream.tell()
            try:
                stream.write(line)
                stream.flush()
                os.fsync(stream.fileno())
            except OSError:
                stream.truncate(position)
                raise
    return target


def remove_temporary(meeting_id: str, session_id: str, seq: int):
    """清理已推送确认片段的所有临时版本，保留其他未确认片段。"""
    if type(seq) is not int or seq < 0:
        raise ValueError("无效的分句序号")
    target = temporary_path(meeting_id, session_id)
    with _LOCK:
        if not target.exists():
            return
        with target.open("r+b") as stream:
            _repair_temporary_tail(stream)
            stream.seek(0)
            remaining = [line.decode("utf-8") for line in stream
                         if json.loads(line)["segment"]["seq"] != seq]
        if remaining:
            staging = None
            try:
                with NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                        prefix=".partial-", suffix=".tmp", delete=False) as stream:
                    staging = Path(stream.name)
                    stream.writelines(remaining)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(staging, target)
            finally:
                if staging:
                    staging.unlink(missing_ok=True)
        else:
            target.unlink()
            for directory in (target.parent, target.parent.parent):
                try:
                    directory.rmdir()
                except OSError:
                    break
