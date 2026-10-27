"""本地设备连接和跨进程执行消息。"""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from src.infrastructure.database.base import Base


class Device(Base):
    __tablename__ = 'devices'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    session_id: Mapped[str] = mapped_column(String(36))
    lease_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DeviceCall(Base):
    __tablename__ = 'device_calls'
    __table_args__ = (Index('idx_device_calls_session_state', 'session_id', 'state'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    device_id: Mapped[str] = mapped_column(ForeignKey('devices.id', ondelete='CASCADE'))
    session_id: Mapped[str] = mapped_column(String(36))
    method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(256))
    query: Mapped[str] = mapped_column(String(2000))
    content_type: Mapped[str] = mapped_column(String(128))
    encrypted_input: Mapped[bytes] = mapped_column(LargeBinary)
    state: Mapped[str] = mapped_column(String(16), server_default='queued')
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    next_seq: Mapped[int] = mapped_column(Integer, server_default='0')
    response_bytes: Mapped[int] = mapped_column(Integer, server_default='0')
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DeviceChunk(Base):
    __tablename__ = 'device_call_chunks'
    call_id: Mapped[str] = mapped_column(ForeignKey('device_calls.id', ondelete='CASCADE'), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
