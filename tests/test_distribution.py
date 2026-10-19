from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


class IsolatedToolsTestCase(unittest.TestCase):
    def test_demo_reopens_without_duplicating_records_or_using_personal_data(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory) / "demo"
            personal = Path(directory) / "personal"
            environment = os.environ.copy()
            environment["SQUACKTS_DATA_HOME"] = str(personal)
            command = [sys.executable, "-m", "scripts.demo", "--home", str(home)]
            for _ in range(2):
                result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, check=True, timeout=30)
                self.assertEqual(json.loads(result.stdout)["orders"], 8)
            with sqlite3.connect(home / "data" / "pod_manager.db") as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 8)
            self.assertFalse(personal.exists())

    def test_demo_refuses_a_nonempty_unmarked_directory(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            original = home / "valuable.txt"
            original.write_text("preservar", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "scripts.demo", "--home", directory], cwd=ROOT,
                capture_output=True, text=True, timeout=30,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(original.read_text(encoding="utf-8"), "preservar")
            self.assertFalse((home / "data").exists())


if __name__ == "__main__":
    unittest.main()
