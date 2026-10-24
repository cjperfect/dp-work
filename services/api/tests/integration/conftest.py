"""只连接显式指定的测试数据库；运行前应用 Alembic 迁移。"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from app.core import config

API_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session", autouse=True)
def migrated_test_database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("请设置 TEST_DATABASE_URL，指向专用测试 PostgreSQL")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(API_ROOT / "alembic.ini"),
            "upgrade",
            "head",
        ],
        check=True,
        env={**os.environ, "DATABASE_URL": url},
    )
    return url


@pytest.fixture(autouse=True)
def test_database(monkeypatch, migrated_test_database):
    monkeypatch.setattr(config, "DATABASE_URL", migrated_test_database)
