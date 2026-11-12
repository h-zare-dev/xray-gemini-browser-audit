import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from session_audit import REGION, consolidate


class CountryBlockTests(unittest.TestCase):
    def test_gemini_current_country_message(self):
        self.assertTrue(REGION.search(
            "Gemini isn’t currently supported in your country. Stay tuned!"
        ))

    def test_country_message_straight_apostrophe(self):
        self.assertTrue(REGION.search(
            "Gemini isn't currently supported in your country."
        ))

    def test_unavailable_region(self):
        self.assertTrue(REGION.search(
            "Gemini is not available in your region"
        ))

    def test_country_block_is_red_without_three_attempts(self):
        from session_audit import state_style
        status, _ = consolidate([("REGION_BLOCKED", "unsupported")])
        self.assertEqual(status, "REGION_BLOCKED")
        self.assertEqual(state_style(status)[1], "BLOCKED")

    def test_linebreaks_in_country_block(self):
        self.assertTrue(REGION.search(
            "Gemini isn’t currently supported\\nin your country. Stay tuned!"
        ))

    def test_missing_textbox_not_region_block(self):
        state, _ = consolidate([("NO_EDITOR", "not visible")] * 2)
        self.assertEqual(state, "NO_EDITOR")


if __name__ == "__main__":
    unittest.main()
