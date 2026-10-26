"""显式注册模型供 Alembic 使用；业务模块不从这里导入其他模块模型。"""

from app.modules.users.models import User
from app.modules.settings.models import UserSettings
from app.modules.knowledge.models import KnowledgeBase, KnowledgeDocument
from app.modules.knowledge.rag_models import KnowledgeParentChunk, KnowledgeChildChunk

from app.modules.meetings.models import Meeting, MeetingSegment, MeetingMinutes, MeetingGenerationJob

from app.modules.meetings.record_models import MeetingRecord, MeetingRecordVersion

from .base import Base

__all__ = ["KnowledgeParentChunk", "KnowledgeChildChunk", "Base", "UserSettings", "User", "KnowledgeBase", "KnowledgeDocument", "Meeting", "MeetingSegment", "MeetingMinutes", "MeetingGenerationJob", "MeetingRecord", "MeetingRecordVersion"]
