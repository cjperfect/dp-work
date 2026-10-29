"""删除废弃 PG 会话表之前，导出独立的本地恢复副本。"""
import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.core import config
import asyncpg

TABLES = ('conversations', 'conversation_messages', 'agent_runs', 'agent_approvals')


async def export(destination):
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    url = config.DATABASE_URL.replace('postgresql+asyncpg://', 'postgresql://')
    db = await asyncpg.connect(url)
    manifest = {'format': 1, 'created_at': datetime.now(timezone.utc).isoformat(), 'tables': {}}
    try:
        async with db.transaction(isolation='repeatable_read', readonly=True):
            for table in TABLES:
                exists = await db.fetchval('SELECT to_regclass($1)', 'public.' + table)
                if not exists:
                    continue
                file = destination / (table + '.jsonl')
                count = 0
                digest = hashlib.sha256()
                with file.open('xb') as target:
                    os.chmod(file, 0o600)
                    async for row in db.cursor(f'SELECT row_to_json(t)::text AS data FROM "{table}" t'):
                        raw = (row['data'] + '\n').encode()
                        target.write(raw)
                        digest.update(raw)
                        count += 1
                    target.flush()
                    os.fsync(target.fileno())
                manifest['tables'][table] = {'count': count, 'sha256': digest.hexdigest()}
        file = destination / 'manifest.json'
        file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        os.chmod(file, 0o600)
        print(json.dumps({'backup': str(destination), 'counts': {k:v['count'] for k,v in manifest['tables'].items()}}))
    finally:
        await db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    asyncio.run(export(parser.parse_args().destination.resolve()))
