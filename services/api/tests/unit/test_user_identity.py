import asyncio
from unittest.mock import AsyncMock

import pytest

from src.core.security import create_access_token, decode_token
from src.modules.users import service


def test_numeric_subject_is_encoded_as_a_string_with_explicit_id_version():
    payload = decode_token(create_access_token(42, "member", "product"))
    assert payload["sub"] == "42"
    assert payload["uidv"] == 2
    assert payload["exp"] - payload["iat"] == 604800


@pytest.mark.parametrize(
    "subject", ["0", "-1", "u-old", "9" * 30, "9223372036854775808", "٤٢", 42, None]
)
def test_invalid_modern_subjects_do_not_query_the_database(monkeypatch, subject):
    lookup = AsyncMock()
    monkeypatch.setattr(service, "find_by_id", lookup)
    assert asyncio.run(service.find_by_subject(subject, 2)) is None
    lookup.assert_not_awaited()


def test_valid_modern_subject_uses_an_integer_lookup(monkeypatch):
    user = object()
    lookup = AsyncMock(return_value=user)
    monkeypatch.setattr(service, "find_by_id", lookup)
    assert asyncio.run(service.find_by_subject("42", 2)) is user
    lookup.assert_awaited_once_with(42)


@pytest.mark.parametrize("version", [None, 1, "2", True, 2.0, 3])
def test_unversioned_and_invalid_tokens_cannot_resolve_users(monkeypatch, version):
    lookup = AsyncMock()
    monkeypatch.setattr(service, "find_by_id", lookup)
    assert asyncio.run(service.find_by_subject("42", version)) is None
    lookup.assert_not_awaited()
