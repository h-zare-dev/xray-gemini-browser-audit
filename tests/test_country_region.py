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

    def test_missing_textbox_not_region_block(self):
        state, _ = consolidate([("NO_EDITOR", "not visible")] * 2)
        self.assertEqual(state, "NO_EDITOR")


if __name__ == "__main__":
    unittest.main()
