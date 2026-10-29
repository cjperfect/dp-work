"""实际文件修改的差异与失败边界。"""
import asyncio
from src.tools.workspace import WorkspaceBackend
from src.tools.file_changes import build_change


def test_write_and_edit_emit_actual_disk_changes(monkeypatch, tmp_path):
    events = []
    monkeypatch.setattr('src.tools.workspace.emit_change', lambda change: events.append(change) if change else None)
    backend = WorkspaceBackend(root_dir=tmp_path, virtual_mode=True)
    assert backend.write('/a.txt', 'one\ntwo\n').error is None
    assert events[0]['additions'] == 2 and events[0]['deletions'] == 0
    async def edit():
        return await backend.aedit('/a.txt', 'two', 'three\nfour')
    assert asyncio.run(edit()).error is None
    assert (tmp_path / 'a.txt').read_text() == 'one\nthree\nfour\n'
    change = events[-1]
    assert change['additions'] == 2 and change['deletions'] == 1
    assert {'kind': 'removed', 'text': 'two'} in change['lines']
    assert {'kind': 'added', 'text': 'four'} in change['lines']
    assert backend.edit('/a.txt', 'missing', 'no').error
    assert len(events) == 2


def test_diff_bounds_and_no_change():
    assert build_change('/a', 'same', 'same') is None
    result = build_change('/a', '', '\n'.join(str(n) for n in range(1000)))
    assert result['additions'] == 1000 and len(result['lines']) == 400 and result['truncated']
    assert build_change('/a', None, 'text')['unavailable']
