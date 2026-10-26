"""按用户保存个人设置，密钥单独加密存储。"""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, JSON, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class UserSettings(Base):
    """个人服务配置表。"""
    __tablename__ = "user_settings"
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    model_config: Mapped[dict] = mapped_column(JSON, default=dict)
    asr_config: Mapped[dict] = mapped_column(JSON, default=dict)
    model_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    asr_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
