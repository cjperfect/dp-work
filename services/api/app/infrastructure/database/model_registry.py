"""显式注册模型供 Alembic 使用；业务模块不从这里导入其他模块模型。"""

from app.modules.meetings.models import Minutes, TranscriptSegment
from app.modules.users.models import User

from .base import Base

__all__ = ["Base", "Minutes", "TranscriptSegment", "User"]
