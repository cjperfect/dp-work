"""捕获成功文件操作的实际差异，不改变工具返回结果。"""
import difflib
import os
import stat
from uuid import uuid4

MAX_BYTES = 256000


def snapshot(path):
    """只读取小型普通 UTF-8 文件；不存在视为空文件。"""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(fd, 'rb') as file:
            if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                return None
            data = file.read(MAX_BYTES + 1)
        return data.decode('utf-8') if len(data) <= MAX_BYTES else None
    except FileNotFoundError:
        return ''
    except (OSError, UnicodeError):
        return None


def build_change(path, before, after):
    """生成有界差异；大文件只返回无法预览的说明。"""
    base = {'id': str(uuid4()), 'path': str(path)}
    if before is None or after is None or max(len(before.splitlines()), len(after.splitlines())) > 5000:
        return {**base, 'unavailable': '文件过大或不是 UTF-8 文本，无法预览差异。', 'lines': [], 'additions': 0, 'deletions': 0}
    if before == after:
        return None
    old, new = before.splitlines(), after.splitlines()
    matcher = difflib.SequenceMatcher(None, old, new)
    additions = deletions = 0
    for tag, a, b, c, d in matcher.get_opcodes():
        if tag in ('replace', 'insert'): additions += d-c
        if tag in ('replace', 'delete'): deletions += b-a
    lines = []
    for group in matcher.get_grouped_opcodes(3):
        if lines: lines.append({'kind': 'context', 'text': '…'})
        for tag, a, b, c, d in group:
            if tag == 'equal': lines.extend({'kind': 'context', 'text': text} for text in old[a:b])
            if tag in ('replace', 'delete'): lines.extend({'kind': 'removed', 'text': text} for text in old[a:b])
            if tag in ('replace', 'insert'): lines.extend({'kind': 'added', 'text': text} for text in new[c:d])
    return {**base, 'additions': additions, 'deletions': deletions, 'lines': lines[:400], 'truncated': len(lines) > 400}


def emit_change(change):
    """通过图事件发送修改记录，非流式调用时跳过。"""
    if change is None: return
    from langgraph.config import get_stream_writer
    try:
        writer = get_stream_writer()
    except RuntimeError:
        return
    writer({'type': 'file_change', 'change': change})
