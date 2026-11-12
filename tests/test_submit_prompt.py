import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import session_audit


class SubmitPromptTests(unittest.TestCase):
    def test_enter_submission_does_not_click_button(self):
        page = MagicMock()
        editor = MagicMock()
        with patch.object(session_audit, "wait_for_submission", return_value=True):
            submitted, detail = session_audit.submit_gemini_prompt(page, editor, "MARKER")
        self.assertTrue(submitted)
        self.assertEqual(detail, "Submitted with Enter")
        page.locator.assert_not_called()

    def test_send_button_fallback_after_enter_is_ignored(self):
        page = MagicMock()
        editor = MagicMock()
        button = page.locator.return_value.nth.return_value
        button.is_visible.return_value = True
        button.is_enabled.return_value = True
        page.locator.return_value.count.return_value = 1
        with (patch.object(session_audit, "wait_for_submission", side_effect=[False, True]),
              patch.object(session_audit, "submission_confirmed", return_value=False)):
            submitted, detail = session_audit.submit_gemini_prompt(page, editor, "MARKER")
        self.assertTrue(submitted)
        self.assertEqual(detail, "Submitted using Send button")
        button.click.assert_called_once()

    def test_unsent_prompt_is_not_reported_as_success(self):
        page = MagicMock()
        editor = MagicMock()
        page.locator.return_value.count.return_value = 0
        with (patch.object(session_audit, "wait_for_submission", return_value=False),
              patch.object(session_audit, "submission_confirmed", return_value=False)):
            submitted, _ = session_audit.submit_gemini_prompt(page, editor, "MARKER")
        self.assertFalse(submitted)


if __name__ == "__main__":
    unittest.main()
