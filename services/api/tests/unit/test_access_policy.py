"""真实 PyCasbin 引擎验证角色独立授权、默认拒绝和 HTTP 权限映射。"""
import pytest
from src.modules.access.policy import DEFAULT_POLICIES, PERMISSIONS, enforcer_for, permissions_for_http


@pytest.mark.parametrize(('role', 'permission', 'allowed'), [
    ('member', 'knowledge:write', True), ('member', 'access:manage', False),
    ('manager', 'knowledge:write', True), ('manager', 'access:manage', False),
    ('viewer', 'knowledge:read', True), ('viewer', 'knowledge:search', True),
    ('viewer', 'meeting:edit', False), ('viewer', 'meeting:archive', False),
    ('viewer', 'meeting:generate', False), ('admin', 'access:manage', True),
    ('unknown', 'knowledge:read', False), ('member', 'unknown', False),
])
def test_enforce(role, permission, allowed):
    assert enforcer_for(DEFAULT_POLICIES).enforce(role, permission) is allowed


def test_revoking_member_policy_does_not_change_other_roles():
    snapshot = tuple(p for p in DEFAULT_POLICIES if p != ('member', 'knowledge:write'))
    enforcer = enforcer_for(snapshot)
    assert not enforcer.enforce('member', 'knowledge:write')
    assert enforcer.enforce('manager', 'knowledge:write')
    assert enforcer.enforce('admin', 'knowledge:write')
    assert all(enforcer.enforce('admin', permission) for permission in PERMISSIONS)


@pytest.mark.parametrize(('method', 'path', 'expected'), [
    ('POST', '/api/knowledge-bases/search', ('knowledge:search',)),
    ('POST', '/api/knowledge-bases/retrieval-capability', ('knowledge:search',)),
    ('DELETE', '/api/knowledge-bases/1', ('knowledge:delete',)),
    ('POST', '/api/meetings/id/minutes/generate', ('meeting:generate',)),
    ('POST', '/api/meetings/id/minutes/archive', ('meeting:archive', 'knowledge:write')),
    ('POST', '/api/meetings/id/record/versions/version/restore', ('meeting:restore',)),
    ('GET', '/api/meetings/shared/records/token', ('meeting:read',)),
    ('POST', '/api/meetings/id/record/share', ('meeting:share',)),
    ('GET', '/api/devices/calls/id/input', ('device:connect',)),
])
def test_http_policy_mapping(method, path, expected):
    assert permissions_for_http(method, path) == expected
