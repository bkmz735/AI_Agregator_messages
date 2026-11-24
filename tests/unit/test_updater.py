import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import updater
import ui_keyboards as kb_ui


class TestUpdater(unittest.IsolatedAsyncioTestCase):

    async def test_get_current_version_info(self):
        info = await updater.get_current_version_info()
        self.assertIsInstance(info, dict)
        self.assertIn("commit", info)
        self.assertIn("date", info)
        self.assertIn("subject", info)
        self.assertIn("branch", info)
        self.assertTrue(len(info["commit"]) > 0)

    def test_check_and_clear_update_flag(self):
        marker = updater.UPDATE_MARKER_FILE
        try:
            marker.write_text("test_commit_123", encoding="utf-8")
            self.assertTrue(marker.exists())
            commit = updater.check_and_clear_update_flag()
            self.assertEqual(commit, "test_commit_123")
            self.assertFalse(marker.exists())
            # Second call when file does not exist
            self.assertIsNone(updater.check_and_clear_update_flag())
        finally:
            marker.unlink(missing_ok=True)

    @patch("updater._run_cmd")
    async def test_check_for_updates_has_diff(self, mock_run_cmd):
        async def fake_run_cmd(*args, **kwargs):
            cmd = " ".join(args)
            if "rev-parse --short HEAD" in cmd:
                return 0, "f2a7956", ""
            elif "fetch origin main" in cmd:
                return 0, "", ""
            elif "rev-parse --short origin/main" in cmd:
                return 0, "abcd123", ""
            elif "log HEAD..origin/main --oneline" in cmd:
                return 0, "abcd123 New cool feature\nef56789 Fix crash", ""
            return 0, "", ""

        mock_run_cmd.side_effect = fake_run_cmd

        res = await updater.check_for_updates()
        self.assertTrue(res["has_updates"])
        self.assertEqual(res["current_commit"], "f2a7956")
        self.assertEqual(res["remote_commit"], "abcd123")
        self.assertEqual(res["commit_count"], 2)
        self.assertIsNone(res["error"])

    @patch("updater._run_cmd")
    async def test_check_for_updates_no_diff(self, mock_run_cmd):
        async def fake_run_cmd(*args, **kwargs):
            cmd = " ".join(args)
            if "rev-parse --short HEAD" in cmd:
                return 0, "f2a7956", ""
            elif "fetch origin main" in cmd:
                return 0, "", ""
            elif "rev-parse --short origin/main" in cmd:
                return 0, "f2a7956", ""
            elif "log HEAD..origin/main --oneline" in cmd:
                return 0, "", ""
            return 0, "", ""

        mock_run_cmd.side_effect = fake_run_cmd

        res = await updater.check_for_updates()
        self.assertFalse(res["has_updates"])
        self.assertEqual(res["commit_count"], 0)

    @patch("updater._run_cmd")
    async def test_apply_update_success(self, mock_run_cmd):
        async def fake_run_cmd(*args, **kwargs):
            cmd = " ".join(args)
            if "checkout -- ." in cmd:
                return 0, "", ""
            elif "pull origin main" in cmd:
                return 0, "Updating f2a7956..abcd123\nFast-forward", ""
            elif "rev-parse --short HEAD" in cmd:
                return 0, "abcd123", ""
            return 0, "", ""

        mock_run_cmd.side_effect = fake_run_cmd

        success, commit = await updater.apply_update()
        self.assertTrue(success)
        self.assertEqual(commit, "abcd123")
        # Cleanup marker file if written
        updater.UPDATE_MARKER_FILE.unlink(missing_ok=True)

    def test_update_keyboards(self):
        kb_no_updates = kb_ui.get_update_keyboard(has_updates=False)
        buttons_no_upd = [b.callback_data for row in kb_no_updates.inline_keyboard for b in row]
        self.assertIn("check_git_updates", buttons_no_upd)
        self.assertNotIn("do_git_update", buttons_no_upd)

        kb_with_updates = kb_ui.get_update_keyboard(has_updates=True)
        buttons_with_upd = [b.callback_data for row in kb_with_updates.inline_keyboard for b in row]
        self.assertIn("check_git_updates", buttons_with_upd)
        self.assertIn("do_git_update", buttons_with_upd)

        kb_progress = kb_ui.get_update_keyboard(in_progress=True)
        progress_texts = [b.text for row in kb_progress.inline_keyboard for b in row]
        self.assertTrue(any("Обновление выполняется" in t for t in progress_texts))


if __name__ == "__main__":
    unittest.main()
