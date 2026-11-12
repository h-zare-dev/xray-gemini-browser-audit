import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from session_audit import consolidate, state_style


class OutcomeTests(unittest.TestCase):
    def test_success_can_stop_early(self):
        status, _ = consolidate([("WEB_OK", "response")])
        self.assertEqual(status, "WEB_OK")

    def test_three_region_rejections_confirm_block(self):
        status, _ = consolidate([("REGION_BLOCKED", "a")] * 3)
        self.assertEqual(status, "REGION_BLOCKED_CONFIRMED")

    def test_mixed_region_is_not_confirmed(self):
        status, _ = consolidate([("REGION_BLOCKED", "a"),
                                  ("RETRYABLE_NETWORK", "b"),
                                  ("REGION_BLOCKED", "c")])
        self.assertEqual(status, "INCONCLUSIVE")

    def test_three_network_errors(self):
        status, _ = consolidate([("RETRYABLE_NETWORK", "a")] * 3)
        self.assertEqual(status, "CONNECTION_FAILED_CONFIRMED")

    def test_candidate_not_green(self):
        status, _ = consolidate([("RESPONSE_CANDIDATE", "a")] * 3)
        self.assertEqual(status, "RESPONSE_CANDIDATE")
        self.assertEqual(state_style(status)[1], "CHECK")


if __name__ == "__main__":
    unittest.main()
