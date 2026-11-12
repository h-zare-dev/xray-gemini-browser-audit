import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from session_audit import make_run_directory


class RunDirectoryTests(unittest.TestCase):
    def test_timestamp_and_collision_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            started_at = datetime(2026, 11, 12, 21, 30, 45, tzinfo=timezone.utc)
            first = make_run_directory(tmp, started_at=started_at)
            (first / "results.csv").write_text("old results", encoding="utf8")
            second = make_run_directory(tmp, started_at=started_at)
            self.assertEqual(first.name, "2026-11-12_21-30-45")
            self.assertEqual(second.name, "2026-11-12_21-30-45_01")
            self.assertEqual((first / "results.csv").read_text(encoding="utf8"), "old results")
            self.assertTrue(second.is_dir())

    def test_missing_base_directory_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = make_run_directory(Path(tmp) / "nested" / "reports")
            self.assertTrue(result.is_dir())


if __name__ == "__main__":
    unittest.main()
