import pytest

from app.infrastructure.database.model_registry import Base
from app.infrastructure.database.session import async_database_url


@pytest.mark.parametrize("scheme", ["sqlite", "sqlite+aiosqlite"])
def test_database_url_uses_aiosqlite(scheme):
    url = async_database_url(f"{scheme}:///./test.db")
    assert url.drivername == "sqlite+aiosqlite"


def test_other_database_driver_is_not_silently_accepted():
    with pytest.raises(ValueError):
        async_database_url("postgresql://user:p%25ss@localhost/db")


def test_model_registry_covers_all_existing_tables():
    assert set(Base.metadata.tables) == {"users", "knowledge_bases", "knowledge_documents"}
