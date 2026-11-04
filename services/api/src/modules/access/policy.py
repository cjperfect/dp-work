"""受控权限目录、默认角色策略及 Casbin 模型。"""
from functools import lru_cache
import casbin

ROLES = ('admin', 'manager', 'member', 'viewer')
PERMISSIONS = (
    'knowledge:read', 'knowledge:write', 'knowledge:delete', 'knowledge:search',
    'meeting:read', 'meeting:write', 'meeting:delete', 'meeting:generate',
    'meeting:edit', 'meeting:share', 'meeting:restore', 'meeting:archive',
    'device:connect', 'access:manage',
)
MEMBER_PERMISSIONS = tuple(value for value in PERMISSIONS if value != 'access:manage')
VIEWER_PERMISSIONS = ('knowledge:read', 'knowledge:search', 'meeting:read', 'device:connect')
DEFAULT_POLICIES = tuple(
    [(role, permission) for role, permissions in (
        ('admin', PERMISSIONS), ('manager', MEMBER_PERMISSIONS), ('member', MEMBER_PERMISSIONS), ('viewer', VIEWER_PERMISSIONS)
    ) for permission in permissions]
)
MODEL = '''
[request_definition]
r = sub, obj
[policy_definition]
p = sub, obj
[role_definition]
g = _, _
[policy_effect]
e = some(where (p.eft == allow))
[matchers]
m = g(r.sub, p.sub) && r.obj == p.obj
'''


@lru_cache(maxsize=32)
def enforcer_for(policies):
    """按完整策略快照缓存纯内存引擎；不缓存数据库授权结果。"""
    model = casbin.Model()
    model.load_model_from_text(MODEL)
    enforcer = casbin.Enforcer(model)
    enforcer.enable_auto_save(False)
    for role, permission in policies:
        enforcer.add_policy(role, permission)
    return enforcer


def permissions_for_http(method, path):
    """业务模块统一映射；权限名称由服务端决定，客户端不能指定。"""
    read = method in ('GET', 'HEAD')
    if path.startswith('/api/knowledge-bases'):
        if path.endswith('/search') or path.endswith('/retrieval-capability'):
            return ('knowledge:search',)
        return ('knowledge:read' if read else 'knowledge:delete' if method == 'DELETE' else 'knowledge:write',)
    if path.startswith('/api/meetings'):
        if read:
            return ('meeting:read',)
        if method == 'DELETE':
            return ('meeting:delete',)
        if path.endswith('/minutes/archive'):
            return ('meeting:archive', 'knowledge:write')
        if path.endswith('/minutes/generate'):
            return ('meeting:generate',)
        if path.endswith('/record/share'):
            return ('meeting:share',)
        if path.endswith('/restore'):
            return ('meeting:restore',)
        if '/record' in path:
            return ('meeting:edit',)
        return ('meeting:write',)
    if path.startswith('/api/devices'):
        return ('device:connect',)
    return ()
