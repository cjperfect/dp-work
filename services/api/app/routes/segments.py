"""转写分句批量写入路由。

性能三原则落地：append-only（只 INSERT）、单语句多行 INSERT + ON CONFLICT DO NOTHING
（单事务幂等）、分句不进 pgvector。
"""
from __future__ import annotations

import uuid as uuidlib
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import db

router = APIRouter(prefix="/api/v1", tags=["segments"])


class SegmentIn(BaseModel):
    id: str | None = Field(default=None, description="分句 id = 幂等键；缺省则生成")
    seq: int
    speaker: str | None = None
    text: str
    start_ms: int | None = None
    end_ms: int | None = None


class SegmentsBatch(BaseModel):
    meeting_id: str
    segments: list[SegmentIn] = Field(max_length=200)


@router.post("/segments")
async def upsert_segments(batch: SegmentsBatch) -> dict[str, int]:
    if not batch.segments:
        return {"written": 0, "ignored": 0}

    pool = await db.get_pool()
    rows: list[tuple[Any, ...]] = []
    for seg in batch.segments:
        seg_id = seg.id or f"{uuidlib.uuid4()}"
        rows.append(
            (
                seg_id,
                batch.meeting_id,
                seg.seq,
                seg.speaker,
                seg.text,
                seg.start_ms,
                seg.end_ms,
            )
        )

    # 单事务多行 INSERT，同 (id) 冲突忽略 → 幂等、append-only
    async with pool.acquire() as conn:
        try:
            result = await conn.executemany(
                """INSERT INTO transcript_segments
                   (id, meeting_id, seq, speaker, text, start_ms, end_ms)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)
                   ON CONFLICT (id) DO NOTHING""",
                rows,
            )
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"写入失败: {e}") from e

    written = result if isinstance(result, int) else 0
    return {"written": written, "ignored": len(rows) - written}
