"""仅用于协议联调的模拟识别流，不消费真实音频。"""
import asyncio
import time

SENTENCES = [
    ("speaker-1", "今天先讨论会议记录和纪要协作的完整流程。"),
    ("speaker-2", "会议结束后生成纪要，并用重点导图回顾结论。"),
    ("speaker-1", "分享链接便于同事补充会议内容。"),
]
STEP_SECONDS = 0.2


async def recognize(stop: asyncio.Event):
    """推送临时文本，停止时只确认已经展示的文本。"""
    origin = time.monotonic()
    for key, (speaker, text) in enumerate(SENTENCES):
        if stop.is_set():
            break
        start = int((time.monotonic()-origin)*1000)
        visible = ""
        for length in range(4, len(text)+4, 4):
            visible = text[:length]
            yield dict(key=key, text=visible, speakerId=speaker, startMs=start,
                       endMs=int((time.monotonic()-origin)*1000), isFinal=False)
            try:
                await asyncio.wait_for(stop.wait(), timeout=STEP_SECONDS)
                break
            except TimeoutError:
                pass
        if visible:
            yield dict(key=key, text=visible, speakerId=speaker, startMs=start,
                       endMs=int((time.monotonic()-origin)*1000), isFinal=True)
        if stop.is_set():
            break


class MockRecognizer:
    mode = "mock"

    def __init__(self):
        self.stop_event = asyncio.Event()

    async def open(self):
        pass

    async def send_audio(self, audio):
        pass

    async def finish(self):
        self.stop_event.set()

    def events(self):
        return recognize(self.stop_event)

    async def close(self):
        self.stop_event.set()
