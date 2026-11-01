"""按本机账号和 Agent 保存知识库关联；云端仍负责访问权限校验。"""
import json
from contextlib import closing
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from ..sessions.storage import SessionStorage, now

AgentCode = Literal['general', 'product', 'ui']
BaseId = Annotated[StrictInt, Field(gt=0, le=9_007_199_254_740_991)]


class KnowledgeLinks(BaseModel):
    """替换单个 Agent 的关联范围，空数组表示主动取消全部关联。"""
    model_config = ConfigDict(extra='forbid')
    agent_code: AgentCode
    knowledge_base_ids: list[BaseId] = Field(max_length=20)


class KnowledgeImport(BaseModel):
    """首次迁移旧配置，不覆盖 SQLite 已有记录，包括已保存的空数组。"""
    model_config = ConfigDict(extra='forbid')
    agents: list[KnowledgeLinks] = Field(max_length=3)


def operation(action, owner, body):
    """读写用户 state.sqlite3；迁移与保存都在单个事务中完成。"""
    changes = KnowledgeLinks.model_validate(body) if action == 'save' else KnowledgeImport.model_validate(body) if action == 'import' else None
    with closing(SessionStorage().connect(owner)) as db, db:
        db.execute('''CREATE TABLE IF NOT EXISTS agent_knowledge_config (
            agent_code TEXT PRIMARY KEY, base_ids_json TEXT NOT NULL, updated_at TEXT NOT NULL)''')
        if changes is not None:
            rows = changes.agents if action == 'import' else [changes]
            for row in rows:
                db.execute('''INSERT INTO agent_knowledge_config VALUES (?,?,?) ON CONFLICT(agent_code) ''' + (
                    'DO NOTHING' if action == 'import' else 'DO UPDATE SET base_ids_json=excluded.base_ids_json, updated_at=excluded.updated_at'),
                    (row.agent_code, json.dumps(list(dict.fromkeys(row.knowledge_base_ids))), now()))
        return {row['agent_code']: json.loads(row['base_ids_json']) for row in db.execute('SELECT * FROM agent_knowledge_config')}
