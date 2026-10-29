"""本地化后仅保留云端仍使用的数据表。"""
import asyncio
from sqlalchemy import text
from src.infrastructure.database import session


def test_cloud_history_tables_are_removed_but_active_tables_remain():
    async def case():
        await session.init_db()
        try:
            async with session.read_session() as db:
                for table in ('conversations','conversation_messages','agent_runs','agent_approvals','user_settings','agent_projects'):
                    assert await db.scalar(text('SELECT to_regclass(:name)'),{'name':'public.'+table}) is None
                for table in ('devices','device_calls','device_call_chunks','users','knowledge_bases','meetings'):
                    assert await db.scalar(text('SELECT to_regclass(:name)'),{'name':'public.'+table}) is not None
        finally:await session.close_db()
    asyncio.run(case())
