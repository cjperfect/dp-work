"""显式注册模型供 Alembic 使用；业务模块不从这里导入其他模块模型。"""

from src.modules.users.models import User
from src.modules.settings.models import UserSettings
from src.modules.knowledge.models import KnowledgeBase, KnowledgeDocument
from src.modules.knowledge.search_models import KnowledgeSearchSync
from src.modules.knowledge.rag_models import KnowledgeParentChunk, KnowledgeChildChunk

from src.modules.meetings.models import Meeting, MeetingSegment, MeetingMinutes, MeetingGenerationJob

from src.modules.meetings.record_models import MeetingRecord, MeetingRecordVersion

from src.infrastructure.tasks.models import TaskOutbox

from src.modules.agents.conversation_models import Conversation, ConversationMessage
from src.modules.agents.project_models import AgentProject
from src.modules.agents.run_models import AgentRun
from src.modules.agents.approval_models import AgentApproval

from src.modules.devices.models import Device, DeviceCall, DeviceChunk

from .base import Base

__all__ = ["Device", "DeviceCall", "DeviceChunk", "AgentRun", "Conversation", "ConversationMessage", "TaskOutbox", "KnowledgeSearchSync", "KnowledgeParentChunk", "KnowledgeChildChunk", "Base", "UserSettings", "User", "KnowledgeBase", "KnowledgeDocument", "Meeting", "MeetingSegment", "MeetingMinutes", "MeetingGenerationJob", "MeetingRecord", "MeetingRecordVersion"]
