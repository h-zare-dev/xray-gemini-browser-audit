import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from vless import outbound_from_url, xray_config


class VlessTests(unittest.TestCase):
    def test_encryption_is_preserved(self):
        sample = "vless://11111111-1111-1111-1111-111111111111@example.org:2001?type=tcp&security=none&encryption=mlkem768x25519plus.random.1rtt.example"
        outbound = outbound_from_url(sample)
        self.assertEqual(outbound["settings"]["vnext"][0]["users"][0]["encryption"], "mlkem768x25519plus.random.1rtt.example")
        result = xray_config(outbound, 23007, 18998)
        self.assertEqual(result["outbounds"][0]["settings"]["vnext"][0]["port"], 23007)
        self.assertEqual(outbound["settings"]["vnext"][0]["port"], 2001)

    def test_port_map_contains_61(self):
        import csv
        with (Path(__file__).parents[1] / "data" / "ports.csv").open() as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 61)
        self.assertEqual(len({int(r["test_port"]) for r in rows}), 61)
