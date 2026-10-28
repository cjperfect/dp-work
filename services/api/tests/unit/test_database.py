import pytest

from src.infrastructure.database.model_registry import Base
from src.infrastructure.database.session import async_database_url


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+asyncpg"])
def test_database_url_uses_asyncpg(scheme):
    url = async_database_url(f"{scheme}://user:p%25ss@localhost/test_db")
    assert url.drivername == "postgresql+asyncpg"
    assert url.password == "p%ss"


def test_other_database_driver_is_not_silently_accepted():
    with pytest.raises(ValueError):
        async_database_url("sqlite:///./test.db")


def test_model_registry_covers_all_existing_tables():
    assert set(Base.metadata.tables) == {"agent_projects", "agent_approvals", "devices", "device_calls", "device_call_chunks", "agent_runs", "conversations", "conversation_messages", "task_outbox", "knowledge_search_sync", "knowledge_parent_chunks", "knowledge_child_chunks", "users", "user_settings", "knowledge_bases", "knowledge_documents", "meetings", "meeting_segments", "meeting_minutes", "meeting_generation_jobs", "meeting_records", "meeting_record_versions"}
