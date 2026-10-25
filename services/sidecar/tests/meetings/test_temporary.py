"""临时片段文件的更新、隔离和清理。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.meetings import repository


class TemporarySegmentTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.object(repository, "TEMP_DIR", Path(self.directory) / "temp"))
        self.segment = dict(id="meeting-1:session-1#0", seq=0, revision=1, text="临时文字", isFinal=False)

    def test_revisions_append_as_lines_and_sessions_are_isolated(self):
        file = repository.save_temporary("meeting-1", "session-1", self.segment)
        updated = {**self.segment, "revision": 2, "text": "新的临时文字\n第二行"}
        repository.save_temporary("meeting-1", "session-1", updated)
        other = repository.save_temporary("meeting-1", "session-2", self.segment)
        lines = file.read_text().splitlines()
        self.assertEqual(file.suffix, ".jsonl")
        self.assertEqual([json.loads(line)["segment"] for line in lines], [self.segment, updated])
        self.assertTrue(file.read_bytes().endswith(b"\n"))
        self.assertEqual(len(list(file.parent.iterdir())), 1)
        repository.remove_temporary("meeting-1", "session-1", 0)
        self.assertFalse(file.exists())
        self.assertTrue(other.exists())

    def test_confirmed_segment_cleanup_preserves_other_segments(self):
        file = repository.save_temporary("meeting-1", "session-1", self.segment)
        repository.save_temporary("meeting-1", "session-1", {**self.segment, "revision": 2})
        pending = {**self.segment, "seq": 1, "text": "另一段"}
        repository.save_temporary("meeting-1", "session-1", pending)
        repository.remove_temporary("meeting-1", "session-1", 0)
        self.assertEqual([json.loads(line)["segment"] for line in file.read_text().splitlines()], [pending])
        repository.remove_temporary("meeting-1", "session-1", 0)
        self.assertTrue(file.exists())
        repository.remove_temporary("meeting-1", "session-1", 1)
        self.assertFalse(file.exists())

    def test_failed_cleanup_preserves_previous_lines_and_cleans_staging_file(self):
        file = repository.save_temporary("meeting-1", "session-1", self.segment)
        repository.save_temporary("meeting-1", "session-1", {**self.segment, "seq": 1})
        original = file.read_bytes()
        with patch.object(repository.os, "replace", side_effect=OSError("test failure")):
            with self.assertRaises(OSError):
                repository.remove_temporary("meeting-1", "session-1", 0)
        self.assertEqual(file.read_bytes(), original)
        self.assertEqual(list(file.parent.iterdir()), [file])

    def test_failed_append_rolls_back_to_previous_lines(self):
        file = repository.save_temporary("meeting-1", "session-1", self.segment)
        original = file.read_bytes()
        with patch.object(repository.os, "fsync", side_effect=OSError("test failure")):
            with self.assertRaises(OSError):
                repository.save_temporary("meeting-1", "session-1", {**self.segment, "revision": 2})
        self.assertEqual(file.read_bytes(), original)

    def test_read_latest_versions_orders_segments_and_missing_file_is_empty(self):
        self.assertEqual(repository.read_temporary("meeting-1", "session-1"), [])
        second = {**self.segment, "id": "meeting-1:session-1#1", "seq": 1}
        repository.save_temporary("meeting-1", "session-1", second)
        repository.save_temporary("meeting-1", "session-1", self.segment)
        updated = {**self.segment, "revision": 3, "text": "最新文字"}
        repository.save_temporary("meeting-1", "session-1", updated)
        repository.save_temporary("meeting-1", "session-1", {**self.segment, "revision": 2})
        self.assertEqual(repository.read_temporary("meeting-1", "session-1"), [updated, second])

    def test_incomplete_tail_is_ignored_then_repaired_before_append(self):
        for tail in (b'{"segment":', b'{"text":"' + "半".encode()[:2]):
            with self.subTest(tail=tail):
                file = repository.save_temporary("meeting-1", "session-1", self.segment)
                with file.open("ab") as stream:
                    stream.write(tail)
                self.assertEqual(repository.read_temporary("meeting-1", "session-1"), [self.segment])
                updated = {**self.segment, "revision": 2}
                repository.save_temporary("meeting-1", "session-1", updated)
                self.assertEqual(repository.read_temporary("meeting-1", "session-1"), [updated])
                self.assertEqual(len(file.read_bytes().splitlines()), 2)
                repository.remove_temporary("meeting-1", "session-1", 0)

    def test_complete_tail_without_newline_is_preserved_before_append(self):
        file = repository.save_temporary("meeting-1", "session-1", self.segment)
        file.write_bytes(file.read_bytes().rstrip(b"\n"))
        updated = {**self.segment, "revision": 2}
        repository.save_temporary("meeting-1", "session-1", updated)
        records = [json.loads(line)["segment"] for line in file.read_bytes().splitlines()]
        self.assertEqual(records, [self.segment, updated])

    def test_cleanup_repairs_incomplete_tail_and_keeps_unconfirmed_segment(self):
        file = repository.save_temporary("meeting-1", "session-1", self.segment)
        pending = {**self.segment, "id": "meeting-1:session-1#1", "seq": 1}
        repository.save_temporary("meeting-1", "session-1", pending)
        with file.open("ab") as stream:
            stream.write(b'{"segment":')
        repository.remove_temporary("meeting-1", "session-1", 0)
        self.assertEqual(repository.read_temporary("meeting-1", "session-1"), [pending])

    def test_invalid_identifiers_cannot_escape_temp(self):
        for value in ["../outside", "a/b", "", "/absolute"]:
            with self.assertRaises(ValueError):
                repository.temporary_path(value, "session-1")
        with self.assertRaises(ValueError):
            repository.save_temporary("meeting-1", "session-1", {**self.segment, "seq": -1})
