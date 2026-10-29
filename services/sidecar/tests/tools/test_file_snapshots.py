"""文件恢复、冲突、Bash 部分失败及路径安全边界。"""
import asyncio
import json
import os
from pathlib import Path

import pytest
from uuid import uuid4

from src import config
from src.tools.file_snapshots import SnapshotBatch, SnapshotError, undo, store_root, workspace_lock
from src.tools.isolation import sandbox_backend
from src.tools.workspace import WorkspaceBackend
from src.tools.file_snapshots import run_changes


@pytest.fixture(autouse=True)
def temporary_store(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path / 'workspaces')


def change_file(root, path, data, owner=7):
    batch = SnapshotBatch(root, owner, [path])
    if data is None:
        (root / path).unlink()
    else:
        (root / path).write_bytes(data)
    return batch.finish()[0]


@pytest.mark.parametrize('before,after', [(None, b''), (None, b'new'), (b'old', b'new'), (b'deleted', None), (b'\x00\xff', b'\x00\xfe')])
def test_create_modify_delete_binary_and_empty_are_restored(tmp_path, before, after):
    root = tmp_path / 'project'
    root.mkdir()
    if before is not None:
        (root / 'a').write_bytes(before)
        (root / 'a').chmod(0o640)
    change = change_file(root, 'a', after)
    assert change['undoable']
    assert undo(7, change['id'], root)['undone']
    assert (root / 'a').exists() == (before is not None)
    if before is not None:
        assert (root / 'a').read_bytes() == before
        if os.name != 'nt':
            assert (root / 'a').stat().st_mode & 0o777 == 0o640
    assert undo(7, change['id'], root)['undone']


def test_later_edits_conflict_and_changes_must_be_undone_backwards(tmp_path):
    first = change_file(tmp_path, 'a', b'one')
    second = change_file(tmp_path, 'a', b'two')
    with pytest.raises(SnapshotError, match='后续修改'):
        undo(7, first['id'], tmp_path)
    (tmp_path / 'a').write_bytes(b'user edit')
    with pytest.raises(SnapshotError, match='后续修改'):
        undo(7, second['id'], tmp_path)
    assert (tmp_path / 'a').read_bytes() == b'user edit'
    (tmp_path / 'a').write_bytes(b'two')
    undo(7, second['id'], tmp_path)
    assert (tmp_path / 'a').read_bytes() == b'one'
    undo(7, first['id'], tmp_path)
    assert not (tmp_path / 'a').exists()


def test_snapshots_are_durable_before_the_write_and_are_account_scoped(tmp_path):
    (tmp_path / 'a').write_bytes(b'original')
    batch = SnapshotBatch(tmp_path, 7, ['a'])
    saved = json.loads((store_root(7) / 'batches' / (batch.id + '.json')).read_text())
    assert (store_root(7) / 'blobs' / saved['files']['a']['hash']).read_bytes() == b'original'
    (tmp_path / 'a').write_bytes(b'changed')
    change = batch.finish()[0]
    with pytest.raises(SnapshotError, match='不存在'):
        undo(8, change['id'], tmp_path)
    with pytest.raises(SnapshotError, match='目录'):
        undo(7, change['id'], tmp_path.parent)


@pytest.mark.skipif(os.name == 'nt', reason='POSIX 软链接安全')
def test_restoring_deleted_file_rejects_parent_symlink(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    (root / 'docs').mkdir()
    (root / 'docs/a').write_bytes(b'original')
    change = change_file(root, 'docs/a', None)
    (root / 'docs').rmdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (root / 'docs').symlink_to(outside, target_is_directory=True)
    with pytest.raises((SnapshotError, OSError)):
        undo(7, change['id'], root)
    assert not (outside / 'a').exists()


def test_busy_workspace_and_large_file_do_not_allow_undo(tmp_path):
    change = change_file(tmp_path, 'a', b'new')
    with workspace_lock(tmp_path):
        with pytest.raises(SnapshotError, match='正在执行'):
            undo(7, change['id'], tmp_path)
    large = change_file(tmp_path, 'large', b'x' * (2 * 1024 * 1024 + 1))
    assert not large['undoable'] and large['undo_unavailable']


def test_corrupt_blob_reference_cannot_escape_snapshot_store(tmp_path):
    (tmp_path / 'a').write_bytes(b'original')
    change = change_file(tmp_path, 'a', b'current')
    manifest = store_root(7) / 'changes' / (change['id'] + '.json')
    record = json.loads(manifest.read_text())
    record['before']['hash'] = '../../outside'
    manifest.write_text(json.dumps(record))
    with pytest.raises(SnapshotError, match='引用无效'):
        undo(7, change['id'], tmp_path)
    assert (tmp_path / 'a').read_bytes() == b'current'


def test_scan_limits_stop_command_before_side_effects(monkeypatch, tmp_path):
    monkeypatch.setattr('src.tools.file_snapshots.MAX_FILES', 0)
    (tmp_path / 'a').write_text('fixture')
    backend = WorkspaceBackend(root_dir=tmp_path, virtual_mode=True)
    result = asyncio.run(backend.aexecute('echo escaped > should-not-exist'))
    assert result.exit_code == 126
    assert not (tmp_path / 'should-not-exist').exists()


@pytest.mark.skipif(sandbox_backend() not in ('macos', 'linux'), reason='真实原生命令沙箱')
@pytest.mark.parametrize('ending', ['exit 1', 'sleep 20'])
def test_bash_diff_captures_partial_failure_and_timeout(monkeypatch, tmp_path, ending):
    root = tmp_path / 'project'
    root.mkdir()
    (root / 'modified').write_text('old\n')
    (root / 'deleted').write_text('restore\n')
    (root / 'node_modules').mkdir()
    (root / 'node_modules/cache').write_text('ignored')
    events = []
    monkeypatch.setattr('src.tools.workspace.emit_change', lambda change: events.append(change))
    backend = WorkspaceBackend(root_dir=root, virtual_mode=True)
    backend._snapshot_owner = 7
    result = asyncio.run(backend.aexecute('echo new > modified; echo created > created; rm deleted; ' + ending, timeout=.2))
    assert result.exit_code in (1, 124)
    assert {Path(event['path']).name for event in events} == {'modified', 'created', 'deleted'}
    assert all(event['undoable'] for event in events)
    for event in events:
        undo(7, event['id'], root)
    assert (root / 'modified').read_text() == 'old\n'
    assert (root / 'deleted').read_text() == 'restore\n'
    assert not (root / 'created').exists()


@pytest.mark.skipif(sandbox_backend() not in ('macos', 'linux'), reason='真实原生命令沙箱')
def test_cancelled_bash_keeps_changes_in_run_index(monkeypatch, tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    monkeypatch.setattr('src.tools.workspace.emit_change', lambda _: None)
    backend = WorkspaceBackend(root_dir=root, virtual_mode=True)
    backend._snapshot_owner = 7
    backend._snapshot_run = str(uuid4())
    async def case():
        task = asyncio.create_task(backend.aexecute('echo pending > a; sleep 20'))
        for _ in range(100):
            if (root / 'a').exists():
                break
            await asyncio.sleep(.02)
        assert (root / 'a').exists()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        changes = run_changes(7, backend._snapshot_run)
        assert len(changes) == 1 and changes[0]['undoable']
        undo(7, changes[0]['id'], root)
        assert not (root / 'a').exists()
    asyncio.run(case())
