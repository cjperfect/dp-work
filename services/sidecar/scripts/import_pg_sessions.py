"""从离线备份幂等迁入本地会话，保留本地修改与删除墓碑。"""
import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.sessions import service


def rows(directory, table, manifest):
    expected = manifest['tables'].get(table)
    if not expected:
        return []
    content = (directory / (table + '.jsonl')).read_bytes()
    if hashlib.sha256(content).hexdigest() != expected['sha256']:
        raise ValueError('备份校验失败：' + table)
    result = [json.loads(line) for line in content.splitlines() if line]
    if len(result) != expected['count']:
        raise ValueError('备份条数不匹配：' + table)
    return result


async def migrate(directory):
    manifest = json.loads((directory/'manifest.json').read_text())
    if manifest['format'] != 1:
        raise ValueError('备份格式不支持。')
    messages = {}
    for row in rows(directory, 'conversation_messages', manifest):
        messages.setdefault(row['conversation_id'], []).append(row)
    imported = skipped = 0
    for row in rows(directory, 'conversations', manifest):
        owner, key = row['owner_id'], row['id']
        nodes = {}
        for message in messages.get(key, []):
            if message['status'] == 'queued':
                continue
            nodes[message['id']] = {'parentId': message['parent_id'], 'message': {
                k: message[k] for k in ('id','role','content','status','context','created_at')}}
        data = {'thread': {k: row[k] for k in ('id','agent_id','title','title_source','draft','created_at','updated_at')},
                'project_id': row.get('project_id'), 'knowledge_base_ids': row['knowledge_base_ids'],
                'messages': [nodes[mid]['message'] for mid in row['active_path'] if mid in nodes],
                'message_branches': list(nodes.values())}
        if row['deleted_at']:
            # 即使重建 SQLite，源端已删除的记录也不能被旧副本重新导入。
            data.update(messages=[],message_branches=[],knowledge_base_ids=[])
            data['thread'].update(title='已删除',draft='')
        if row['deleted_at']:
            from src.sessions.storage import SessionError
            try:
                await service.io(service.storage.get, owner, key, True)
                skipped += 1
                continue
            except SessionError as cause:
                if cause.status != 404:
                    raise
        result = await service.operation('import', {'owner_id': owner, 'body': data})
        if result is not None and row['deleted_at']:
            await service.operation('delete', {'owner_id': owner, 'thread_id': key})
        if result is None:
            skipped += 1
        else:
            imported += 1
            if not row['deleted_at']:
                restored = await service.operation('get', {'owner_id': owner, 'thread_id': key})
                # 旧分支不覆盖本地修改；导入成功后必须能够读取有效会话。
                if restored['thread']['id'] != key:
                    raise ValueError('迁移读取校验失败。')
    print(json.dumps({'processed': imported, 'kept_tombstones': skipped}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('backup',type=Path)
    asyncio.run(migrate(parser.parse_args().backup.resolve()))
