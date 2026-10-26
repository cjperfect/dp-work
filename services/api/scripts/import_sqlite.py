"""将 SQLite 业务数据迁入空的 PostgreSQL，保留原 ID 和富文本内容。"""
import argparse
import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import DateTime, Integer, JSON, func, select, text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import DATABASE_URL
from app.infrastructure.database.model_registry import Base
from app.infrastructure.database.session import async_database_url


async def import_database(source: Path, target_url: str) -> dict[str, int]:
    """在单个事务内导入数据；目标库非空时拒绝覆盖。"""
    source = source.resolve(strict=True)
    engine = create_async_engine(async_database_url(target_url), hide_parameters=True)
    counts = {}
    try:
        with sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True) as sqlite:
            sqlite.row_factory = sqlite3.Row
            tables = {row[0] for row in sqlite.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            async with engine.begin() as connection:
                for table in Base.metadata.sorted_tables:
                    if await connection.scalar(select(func.count()).select_from(table)):
                        raise ValueError(f"目标表 {table.name} 非空，已拒绝覆盖。")
                for table in Base.metadata.sorted_tables:
                    if table.name not in tables:
                        continue
                    # 表和列名只取自受信任的 ORM 元数据。
                    rows = sqlite.execute(f'SELECT * FROM "{table.name}"')
                    count = 0
                    while batch := rows.fetchmany(500):
                        values = []
                        for row in batch:
                            value = dict(row)
                            for column in table.columns:
                                item = value.get(column.name)
                                if isinstance(column.type, JSON) and isinstance(item, str):
                                    value[column.name] = json.loads(item)
                                elif isinstance(column.type, DateTime) and isinstance(item, str):
                                    time = datetime.fromisoformat(item)
                                    value[column.name] = time if time.tzinfo else time.replace(tzinfo=timezone.utc)
                            values.append(value)
                        await connection.execute(table.insert(), values)
                        count += len(values)
                    counts[table.name] = count
                for table in Base.metadata.sorted_tables:
                    primary = list(table.primary_key.columns)
                    if len(primary) == 1 and isinstance(primary[0].type, Integer):
                        column = primary[0]
                        sequence = await connection.scalar(text("SELECT pg_get_serial_sequence(:table, :column)"),
                                                           {"table": table.name, "column": column.name})
                        if sequence:
                            maximum = await connection.scalar(select(func.max(column)))
                            await connection.execute(text("SELECT setval(CAST(:sequence AS regclass), :value, :used)"),
                                                     {"sequence": sequence, "value": maximum or 1, "used": maximum is not None})
        return counts
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="原 SQLite 文件；目标从 DATABASE_URL 读取")
    args = parser.parse_args()
    result = asyncio.run(import_database(args.source, DATABASE_URL))
    for table, count in result.items():
        print(f"{table}: {count} rows")
