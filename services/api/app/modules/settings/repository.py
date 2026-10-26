"""个人配置数据访问。"""
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from .models import UserSettings


class SettingsRepository:
    """按用户隔离配置记录。"""
    def __init__(self, conn):
        self.conn = conn

    async def get(self, owner_id: int, lock=False):
        """读取当前用户配置。"""
        statement = select(UserSettings).where(UserSettings.owner_id == owner_id)
        if lock:
            statement = statement.with_for_update()
        return await self.conn.scalar(statement)

    async def ensure(self, owner_id: int):
        """创建配置记录，兼容并发首次保存。"""
        await self.conn.execute(insert(UserSettings).values(owner_id=owner_id, model_config={}, asr_config={}).on_conflict_do_nothing())
        return await self.get(owner_id, lock=True)
