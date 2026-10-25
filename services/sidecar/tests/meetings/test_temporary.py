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
        self.segment = dict(seq=0, revision=1, text="临时文字", isFinal=False)

    def test_new_revisions_replace_one_file_and_sessions_are_isolated(self):
        file = repository.save_temporary("meeting-1", "session-1", self.segment)
        updated = {**self.segment, "revision": 2, "text": "新的临时文字"}
        repository.save_temporary("meeting-1", "session-1", updated)
        other = repository.save_temporary("meeting-1", "session-2", self.segment)
        self.assertEqual(json.loads(file.read_text())["segment"], updated)
        self.assertEqual(len(list(file.parent.iterdir())), 1)
        repository.remove_temporary("meeting-1", "session-1", 0)
        self.assertFalse(file.exists())
        self.assertTrue(other.exists())

    def test_failed_replacement_preserves_previous_text_and_cleans_staging_file(self):
        file = repository.save_temporary("meeting-1", "session-1", self.segment)
        with patch.object(repository.os, "replace", side_effect=OSError("test failure")):
            with self.assertRaises(OSError):
                repository.save_temporary("meeting-1", "session-1", {**self.segment, "revision": 2})
        self.assertEqual(json.loads(file.read_text())["segment"], self.segment)
        self.assertEqual(list(file.parent.iterdir()), [file])

    def test_invalid_identifiers_cannot_escape_temp(self):
        for value in ["../outside", "a/b", "", "/absolute"]:
            with self.assertRaises(ValueError):
                repository.segment_path(value, "session-1", 0)
        with self.assertRaises(ValueError):
            repository.segment_path("meeting-1", "session-1", -1)
