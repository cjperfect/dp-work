"""会议生成状态的登录用户订阅。"""
from fastapi import APIRouter, WebSocket
from src.infrastructure.realtime.state_events import state_events
from . import service

router = APIRouter()


async def snapshot(owner):
    meetings = await service.list_meetings(owner)
    return {"type": "meetings.snapshot", "meetings": [row.model_dump(mode="json") for row in meetings]}


async def update(owner, event):
    # 更新只含列表元数据，正文由详情页按需读取。
    meetings = await service.list_meetings(owner)
    row = next((row for row in meetings if row.id == event.get("meeting_id")), None)
    if row:
        return [{"type": "meeting.updated", "meeting": row.model_dump(mode="json")}]
    return [{"type": "meeting.removed", "meeting_id": event["meeting_id"]}]


@router.websocket("/events")
async def meeting_events(websocket: WebSocket):
    await state_events(websocket, permission="meeting:read", channel="meeting_generation",
                       snapshot=snapshot, update=update)
