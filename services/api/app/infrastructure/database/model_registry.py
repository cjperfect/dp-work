"""显式注册模型供 Alembic 使用；业务模块不从这里导入其他模块模型。"""

from app.modules.users.models import User
from app.modules.knowledge.models import KnowledgeBase, KnowledgeDocument

from .base import Base

__all__ = ["Base", "User", "KnowledgeBase", "KnowledgeDocument"]
