"""The honeypot EFSM must return the PX4 SITL ACK for every captured test row."""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "efsm"))


@unittest.skipUnless(importlib.util.find_spec("pymavlink"), "Install requirements-tlog.txt to check the EFSM")
class EfsmGroundTruthTests(unittest.TestCase):
    def test_every_px4_test_row_matches(self):
        from check_efsm import check
        rows = check(ROOT / "efsm" / "ack_capture.csv")
        self.assertEqual(len(rows), 117)
        mismatches = [r for r in rows if not r["match"]]
        self.assertEqual(mismatches, [], f"{len(mismatches)} rows differ from PX4")


if __name__ == "__main__":
    unittest.main()
