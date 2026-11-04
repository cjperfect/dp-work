"""文档解析状态的登录用户订阅。"""
from fastapi import APIRouter, WebSocket
from src.infrastructure.realtime.state_events import state_events
from .parsing import parse_states

router = APIRouter()


async def snapshot(owner):
    return {"type": "documents.snapshot", "documents": await parse_states(owner)}


async def update(owner, event):
    states = await parse_states(owner, event.get("document_id"))
    return [{"type": "document.updated", "document": state} for state in states]


@router.websocket("/events")
async def document_events(websocket: WebSocket):
    await state_events(websocket, permission="knowledge:read", channel="document_parsing",
                       snapshot=snapshot, update=update)
