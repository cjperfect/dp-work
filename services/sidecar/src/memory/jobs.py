"""SQLite 持久进度、带租约领取及原子合并，不保存聊天副本。"""
import json
import time
from uuid import uuid4

from . import repository as repo
from .pipeline import digest, redact, safe_text
from .schemas import MemoryWrite

LEASE_SECONDS = 300
MAX_ATTEMPTS = 3


def signatures(state):
    """原分支内容变化会使任务失效，已处理消息只保留摘要。"""
    rows = []
    for mid in state['active_path']:
        row = state['nodes'][mid]
        rows.append((mid, digest(json.dumps({key: row.get(key) for key in ('role', 'content', 'status', 'created_at')}, ensure_ascii=False))))
    fingerprint = digest(json.dumps([state['thread']['updated_at'], state['thread'].get('project_id'), rows], ensure_ascii=False))
    return fingerprint, rows


def inactive(state):
    """排除运行中、待审批、未完成或有草稿的会话。"""
    if state.get('deleted') or state['thread'].get('draft') or not state['active_path']:
        return False
    if any(row['status'] == 'running' for row in state.get('runs', {}).values()):
        return False
    last = state['nodes'][state['active_path'][-1]]
    return last['role'] == 'assistant' and last['status'] == 'complete' and bool(last['content'].strip())


def prepare(owner, state, root):
    """领取新内容或到期重试任务，崩溃后租约过期可恢复。"""
    if not inactive(state):
        return None
    fingerprint, inputs = signatures(state)
    thread = state['thread']['id']
    now = time.time()
    with repo.connection(owner, root, True) as db:
        prefs = dict(db.execute('SELECT * FROM preferences WHERE id=1').fetchone())
        if not prefs['auto_generate']:
            return None
        job = db.execute('SELECT * FROM memory_jobs WHERE thread_id=?', (thread,)).fetchone()
        if job and job['status'] == 'running' and job['lease_until'] > now:
            return None
        same = job and job['fingerprint'] == fingerprint
        if same and job['status'] == 'running' and job['attempts'] >= MAX_ATTEMPTS:
            db.execute("UPDATE memory_jobs SET status='retry',error_code='LEASE_EXPIRED' WHERE thread_id=?", (thread,))
            return None
        if same and (job['status'] == 'done' or job['attempts'] >= MAX_ATTEMPTS or job['retry_at'] > now):
            return None
        previous = dict(db.execute('SELECT message_id,digest FROM memory_inputs WHERE thread_id=?', (thread,)))
        messages = []
        for mid, value in inputs:
            row = state['nodes'][mid]
            if previous.get(mid) == value or row.get('created_at', '') <= prefs['forget_before']:
                continue
            if row['role'] not in ('user', 'assistant') or row['status'] != 'complete':
                continue
            text = redact(row['content'][:3000])
            if not text.strip():
                continue
            tools = [{'name': call['name'], 'result': redact(str(call.get('result', ''))[:600])}
                     for call in row.get('context', {}).get('tool_calls', []) if call.get('status') == 'complete'][:4]
            messages.append({'id': mid, 'role': row['role'], 'text': text, 'successful_tools': tools})
        messages = messages[-24:]
        # 从最新记录保留完整短消息，限制每次发送的内容量。
        while len(json.dumps(messages, ensure_ascii=False)) > 24000:
            messages.pop(0)
        token = str(uuid4())
        attempt = job['attempts'] + 1 if same else 1
        db.execute('INSERT OR REPLACE INTO memory_jobs VALUES(?,?,?,?,?,?,?,?,?,?)',
                   (thread, fingerprint, 'running', attempt, 0, now + LEASE_SECONDS, token, None, repo.timestamp(), state['thread']['updated_at']))
        return {'owner': owner, 'thread_id': thread, 'fingerprint': fingerprint, 'token': token,
                'epoch': prefs['generation_epoch'], 'inputs': inputs, 'attempts': attempt,
                'snapshot': {'agent_code': {1: 'general', 2: 'product', 3: 'ui'}[state['thread']['agent_id']],
                             'project_id': state['thread'].get('project_id'), 'messages': messages}}


def existing(owner, snapshot, candidates, root):
    """只向合并器提供当前范围内的少量相关记录。"""
    rows = []
    with repo.connection(owner, root) as db:
        for row in db.execute("SELECT * FROM memories WHERE scope='user' OR (scope='agent' AND scope_id=?) OR (scope='project' AND scope_id=?)",
                              (snapshot['agent_code'], snapshot['project_id'] or '')):
            rows.append(dict(row))
    words = set(''.join(item['title'] for item in candidates).casefold())
    rows.sort(key=lambda row: (repo.key_for(row['title']) not in {repo.key_for(item['title']) for item in candidates},
                               -len(words.intersection(row['title'].casefold())), row['id']))
    result = []
    for row in rows[:40]:
        item = repo.outward(row)
        if not safe_text(item['content'] + '\n' + item['title']):
            continue
        if len(json.dumps([*result, item], ensure_ascii=False)) <= 24000:
            result.append(item)
    return result


def target(item, snapshot):
    return snapshot['agent_code'] if item['scope'] == 'agent' else snapshot['project_id'] if item['scope'] == 'project' else ''


def commit(owner, job, state, candidates, decisions, known, root):
    """会话、开关和人工编辑未变化时，一次事务提交记忆及完成标记。"""
    if not inactive(state) or signatures(state)[0] != job['fingerprint']:
        return False
    with repo.connection(owner, root, True) as db:
        current = db.execute('SELECT * FROM memory_jobs WHERE thread_id=?', (job['thread_id'],)).fetchone()
        prefs = db.execute('SELECT * FROM preferences WHERE id=1').fetchone()
        if not current or current['token'] != job['token'] or current['status'] != 'running' or current['lease_until'] <= time.time():
            return False
        if not prefs['auto_generate'] or prefs['generation_epoch'] != job['epoch']:
            return False
        known = {item['id']: item for item in known}
        changed = 0
        for decision in decisions:
            if decision['action'] == 'skip':
                continue
            item = candidates[decision['candidate']]
            scope_id = target(item, job['snapshot'])
            if scope_id is None or not safe_text(item['title'] + '\n' + item['content']):
                continue
            content = decision.get('content') if decision['action'] == 'update' else item['content']
            if not content or not safe_text(content):
                continue
            key = repo.key_for(item['title'])
            exclusions = db.execute('SELECT key_hash,content_hash FROM memory_exclusions').fetchall()
            if any(row['key_hash'] == digest(key) or row['content_hash'] in (digest(repo.key_for(item['content'])), digest(repo.key_for(content))) for row in exclusions):
                continue
            old = None
            if decision['action'] == 'update':
                reference = known.get(decision.get('target_id'))
                if not reference:
                    continue
                old = db.execute('SELECT * FROM memories WHERE id=?', (reference['id'],)).fetchone()
                if not old or old['revision'] != reference['revision']:
                    return False
                if old['source'] != 'automatic' or not old['enabled'] or (old['expires_at'] and old['expires_at'] <= repo.timestamp()):
                    continue
                if old['scope'] != item['scope'] or old['scope_id'] != scope_id or old['kind'] != item['kind']:
                    continue
                identifier, title, key = old['id'], old['title'], old['memory_key']
            else:
                # 模型漏判同名或相同正文时，数据库仍拒绝重复新增。
                duplicate = any(row['memory_key'] == key or repo.key_for(row['content']) == repo.key_for(content)
                                for row in db.execute('SELECT memory_key,content FROM memories WHERE scope=? AND scope_id=?', (item['scope'], scope_id)))
                if duplicate or db.execute('SELECT COUNT(*) FROM memories').fetchone()[0] >= 1000:
                    continue
                identifier, title = str(uuid4()), item['title']
            data = MemoryWrite(title=title, content=content, kind=item['kind'], scope=item['scope'],
                               agent_code=scope_id if item['scope'] == 'agent' else None,
                               project_id=scope_id if item['scope'] == 'project' else None)
            if old and old['content'] == data.content:
                continue
            stamp, revision = repo.timestamp(), old['revision'] + 1 if old else 1
            if old:
                db.execute('UPDATE memories SET content=?,revision=?,updated_at=? WHERE id=?',
                           (data.content, revision, stamp, identifier))
            else:
                db.execute('INSERT INTO memories VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                           (identifier, data.title, key, data.content, data.kind, data.scope, scope_id, 1, revision, 'automatic', stamp, stamp, None))
            result = repo.outward(db.execute('SELECT * FROM memories WHERE id=?', (identifier,)).fetchone())
            db.execute('INSERT INTO memory_revisions VALUES(?,?,?,?)', (identifier, revision, json.dumps(result, ensure_ascii=False), stamp))
            db.execute('INSERT OR REPLACE INTO memory_origins VALUES(?,?,?,?)', (identifier, job['thread_id'], job['fingerprint'], stamp))
            changed += 1
        db.executemany('INSERT OR REPLACE INTO memory_inputs VALUES(?,?,?)', [(job['thread_id'], mid, value) for mid, value in job['inputs']])
        db.execute("UPDATE memory_jobs SET status='done',lease_until=0,error_code=NULL,updated_at=? WHERE thread_id=? AND token=?",
                   (repo.timestamp(), job['thread_id'], job['token']))
        if changed:
            db.execute('UPDATE preferences SET generation_epoch=generation_epoch+1 WHERE id=1')
        return True


def fail(owner, job, code, root, cancelled=False):
    """只保存安全错误码，有限退避重试，不保存上游输出或凭证。"""
    with repo.connection(owner, root, True) as db:
        db.execute("UPDATE memory_jobs SET status='retry',lease_until=0,retry_at=?,error_code=?,attempts=CASE WHEN ? THEN MAX(0,attempts-1) ELSE attempts END,updated_at=? WHERE thread_id=? AND token=? AND status='running'",
                   (time.time() + (10 if cancelled else 60 * 2 ** min(3, job.get('attempts', 1))), code, cancelled,
                    repo.timestamp(), job['thread_id'], job['token']))
