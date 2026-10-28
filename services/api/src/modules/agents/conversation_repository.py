"""仅提供账号范围内的会话和消息读写。"""
from sqlalchemy import delete, select
from .conversation_models import Conversation, ConversationMessage


class ConversationRepository:
    def __init__(self, db):
        self.db = db

    async def get(self, owner, key, lock=False, deleted=False):
        """锁定时同样限制归属，删除墓碑仅供幂等判断。"""
        query = select(Conversation).where(Conversation.id == key, Conversation.owner_id == owner)
        if not deleted: query = query.where(Conversation.deleted_at.is_(None))
        return await self.db.scalar(query.with_for_update() if lock else query)

    async def list(self, owner, q='', agent_id=None):
        """只读取列表元数据，按最近活动排序。"""
        query = select(Conversation.id, Conversation.agent_id, Conversation.project_id, Conversation.title, Conversation.title_source,
            Conversation.draft_revision, Conversation.created_at, Conversation.updated_at).where(Conversation.owner_id == owner, Conversation.deleted_at.is_(None))
        if q.strip(): query = query.where(Conversation.title.icontains(q.strip(), autoescape=True))
        if agent_id: query = query.where(Conversation.agent_id == agent_id)
        return (await self.db.execute(query.order_by(Conversation.updated_at.desc(), Conversation.id))).mappings().all()

    async def messages(self, key):
        """读取分支节点，选中路径由会话元数据指定。"""
        return (await self.db.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == key)
            .order_by(ConversationMessage.created_at, ConversationMessage.id))).all()

    async def clear_messages(self, key):
        """在调用方事务内清理消息。"""
        await self.db.execute(delete(ConversationMessage).where(ConversationMessage.conversation_id == key))
