"""WebSocket 控制消息。"""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, TypeAdapter


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AudioFormat(Message):
    format: Literal["pcm"]
    sampleRate: StrictInt = Field(ge=16000, le=16000)
    channels: StrictInt = Field(ge=1, le=1)
    bitsPerSample: StrictInt = Field(ge=16, le=16)


class Start(Message):
    type: Literal["asr.start"]
    requestId: str = Field(min_length=1, max_length=128)
    meetingId: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    audio: AudioFormat
    nextSeq: StrictInt = Field(ge=0, le=9_007_199_254_740_991)
    offsetMs: StrictInt = Field(ge=0, le=9_007_199_254_740_991)


class Stop(Message):
    type: Literal["asr.stop"]
    requestId: str = Field(min_length=1, max_length=128)
    meetingId: str = Field(min_length=1, max_length=128)


control_message = TypeAdapter(Annotated[Start | Stop, Field(discriminator="type")])
