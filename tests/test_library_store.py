from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from core.library import LibraryStore


class LibraryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.recordings = self.root / "recordings"
        self.metadata = self.recordings / "library.json"
        self.store = LibraryStore(self.recordings, self.metadata)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _recording(self, name: str, recorded_at: datetime) -> Path:
        path = self.recordings / name
        path.write_bytes(b"RIFF")
        timestamp = recorded_at.timestamp()
        os.utime(path, (timestamp, timestamp))
        self.store.register_raw(path, 5.0)
        return path

    def test_favorite_sort_puts_hearts_first_then_keeps_time_order(self) -> None:
        older = self._recording("older.wav", datetime(2026, 7, 15, 9, 0))
        newer = self._recording("newer.wav", datetime(2026, 7, 15, 12, 0))
        next_day = self._recording("next-day.wav", datetime(2026, 7, 16, 8, 0))
        self.store.set_favorite(older, True)

        self.assertEqual(
            [entry.path for entry in self.store.entries(sort_mode="time")],
            [next_day, newer, older],
        )
        self.assertEqual(
            [entry.path for entry in self.store.entries(sort_mode="favorite")],
            [older, next_day, newer],
        )

    def test_keeping_one_hum_deletes_other_recordings_from_same_day(self) -> None:
        kept = self._recording("kept.wav", datetime(2026, 7, 15, 9, 0))
        removed = self._recording("removed.wav", datetime(2026, 7, 15, 12, 0))
        next_day = self._recording("next-day.wav", datetime(2026, 7, 16, 8, 0))

        deleted = self.store.keep_only_for_day(kept, "#90B8DC")

        self.assertEqual(deleted, [removed])
        self.assertTrue(kept.exists())
        self.assertFalse(removed.exists())
        self.assertTrue(next_day.exists())
        self.assertTrue(self.store.has_kept_recording_for_day(date(2026, 7, 15)))
        self.assertFalse(self.store.has_kept_recording_for_day(date(2026, 7, 16)))
        kept_entry = next(entry for entry in self.store.entries() if entry.path == kept)
        self.assertTrue(kept_entry.kept)
        self.assertEqual(kept_entry.color, "#90B8DC")


if __name__ == "__main__":
    unittest.main()
