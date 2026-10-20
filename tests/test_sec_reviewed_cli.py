"""No network, synthetic example only."""
import json
import pathlib
import tempfile
import unittest
from sec_reviewed_cli import main
from test_sec_companyfacts import fixture
from test_sec_v02_bridge import PROPOSAL


class ReviewedCliTests(unittest.TestCase):
    def test_cli_records_and_writes_result(self):
        with tempfile.TemporaryDirectory() as temp:
            p = pathlib.Path(temp)
            paths = {}
            for name, obj in (("companyfacts", fixture()), ("proposal", PROPOSAL),
                              ("fy_ends", ["2025-12-31", "2026-12-31", "2027-12-31"])):
                path = p / (name + ".json")
                path.write_text(json.dumps(obj), encoding="utf-8")
                paths[name] = str(path)
            main(["--companyfacts", paths["companyfacts"], "--as-of", "2025-03-01",
                  "--proposal", paths["proposal"], "--fy-ends", paths["fy_ends"],
                  "--db", str(p / "forecasts.sqlite"), "--out", str(p / "report.json")])
            self.assertEqual(json.loads((p / "report.json").read_text())["forecast_rows"], 9)


if __name__ == "__main__":
    unittest.main()
