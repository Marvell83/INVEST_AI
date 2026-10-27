"""Offline regression tests for Windows INVEST_AI application launcher."""
from __future__ import annotations

import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

from invest_ai_masaustu import (
    STATIC_FILES, local_sec_contact, prepare_workspace,
    self_test, workspace_path,
)
from invest_ai_web import ResearchService


class WindowsDesktopLauncherTests(unittest.TestCase):
    @staticmethod
    def _sample_assets(root, *, marker="old"):
        for relative in STATIC_FILES:
            path = Path(root) / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("content-" + marker + " " + relative, encoding="utf-8")

    def test_windows_workspace_is_localappdata_not_exe_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            root = workspace_path({"LOCALAPPDATA": folder})
            self.assertEqual(root, (Path(folder) / "INVEST_AI").resolve())

    def test_static_updates_preserve_sec_database_zip_reports_and_email(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "bundle"
            target = Path(folder) / "user"
            self._sample_assets(source)
            prepare_workspace(source=source, destination=target)
            files = {
                "veri/companyfacts.zip": b"SEC raw ZIP bytes must survive",
                "veri/invest_ai_evren.sqlite3": b"SQLite data must survive",
                "reports/research/saved-report.json": b"Saved research must survive",
            }
            for name, value in files.items():
                p = target / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(value)
            conf = target / "SEC_USER_AGENT.txt"
            conf.write_text("SEC_USER_AGENT=INVEST_AI my-real-email@work.example\n",
                            encoding="utf-8")
            self._sample_assets(source, marker="updated")
            self.assertEqual(prepare_workspace(source=source, destination=target), target.resolve())
            for name, value in files.items():
                self.assertEqual((target / name).read_bytes(), value)
            self.assertEqual(local_sec_contact(target),
                             "INVEST_AI my-real-email@work.example")
            self.assertIn("content-updated", (target / "index.html").read_text())

    def test_sec_email_file_is_optional_for_offline_use(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "bundle"
            destination = Path(folder) / "user"
            self._sample_assets(source)
            prepare_workspace(source=source, destination=destination)
            self.assertEqual(local_sec_contact(destination), "")
            with patch.dict("os.environ", {"SEC_USER_AGENT":"INVEST_AI name@example.net"}):
                self.assertEqual(local_sec_contact(destination), "INVEST_AI name@example.net")
            (destination / "SEC_USER_AGENT.txt").write_text(
                "# no contact\nSEC_USER_AGENT=INVEST_AI named-contact@example.com\n",
                encoding="utf-8")
            self.assertEqual(local_sec_contact(destination),
                             "INVEST_AI named-contact@example.com")

    def test_health_endpoint_runs_in_local_only_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "bundle"
            destination = Path(folder) / "user"
            self._sample_assets(source)
            root = prepare_workspace(source=source, destination=destination)
            app = ResearchService(root=root, user_agent="")
            output = io.StringIO()
            with redirect_stdout(output):
                self_test(root, app)
            self.assertIn("INVEST_AI_WINDOWS_SELF_TEST_OK", output.getvalue())
            self.assertIn("invest-ai-web", output.getvalue())

    def test_missing_bundled_asset_blocks_broken_release(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(FileNotFoundError, "index.html"):
                prepare_workspace(source=Path(folder)/"missing",
                                  destination=Path(folder)/"user")


if __name__ == "__main__":
    unittest.main()
