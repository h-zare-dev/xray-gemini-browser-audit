import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sources import ports_from_spec, subscription_links, targets_from_env


class SourcesTests(unittest.TestCase):
    def test_ports_ranges_and_duplicates(self):
        self.assertEqual(ports_from_spec("21001-21003,24001,21002,25001-25002"),
                         [21001, 21002, 21003, 24001, 25001, 25002])

    def test_invalid_ports(self):
        for value in ("0", "65536", "24009-24001", "21001-xxx", ""):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    ports_from_spec(value)

    def test_plain_subscription(self):
        link = "vless://11111111-1111-1111-1111-111111111111@server.example:443?type=tcp#Paris"
        self.assertEqual(subscription_links(link), [link])

    def test_base64_subscription(self):
        import base64
        link = "vless://11111111-1111-1111-1111-111111111111@server.example:443#Paris"
        data = base64.b64encode((link + "\n").encode()).decode()
        self.assertEqual(subscription_links(data), [link])

    def test_single_vless(self):
        env = {
            "MODE": "vless",
            "VLESS_URL": "vless://11111111-1111-1111-1111-111111111111@server.example:443",
            "PORTS": "23001,23004,23007",
        }
        targets, skipped = targets_from_env(env)
        self.assertEqual([t.port for t in targets], [23001,23004,23007])
        self.assertEqual(skipped, [])

    def test_subscription_preserves_own_ports_and_reports_skips(self):
        text = ("vless://11111111-1111-1111-1111-111111111111@a.example:2053#A\n"
                "trojan://password@b.example:443#B\n"
                "vless://11111111-1111-1111-1111-111111111111@c.example:8443#C")
        with patch("sources.fetch_subscription", return_value=text):
            targets, skipped = targets_from_env({"MODE": "subscription", "SUBSCRIPTION_URL": "https://example.org/s"})
        self.assertEqual([t.port for t in targets], [2053,8443])
        self.assertEqual(len(skipped), 1)


if __name__ == "__main__":
    unittest.main()
