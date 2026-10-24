import pytest
from app.infrastructure.database.model_registry import Base
from app.infrastructure.database.session import async_database_url


@pytest.mark.parametrize("scheme", ["postgresql", "postgres", "postgresql+asyncpg"])
def test_database_url_uses_asyncpg(scheme):
    url = async_database_url(f"{scheme}://user:p%25ss@localhost/db")
    assert url.drivername == "postgresql+asyncpg"
    assert url.password == "p%ss"


def test_other_database_driver_is_not_silently_accepted():
    with pytest.raises(ValueError):
        async_database_url("sqlite:///test.db")


def test_model_registry_covers_all_existing_tables():
    assert set(Base.metadata.tables) == {"users", "minutes", "transcript_segments"}
    assert {
        tuple(column.name for column in constraint.columns)
        for constraint in Base.metadata.tables["transcript_segments"].constraints
    } >= {("id",), ("meeting_id", "seq")}
