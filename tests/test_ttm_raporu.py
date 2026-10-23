"""Offline Turkish HTML presentation tests: synthetic accounting and source records."""
import json
from pathlib import Path
import tempfile
import unittest

from ttm_finansallar import calculate_ttm
from ttm_dcf_bridge import run_ttm_scenarios
from ttm_raporu import render_ttm, main

ROOT=Path(__file__).resolve().parent.parent
SAMPLE=ROOT/"ornekler/apple_ttm_evidence_2026-10-21.json"
SCENARIOS=ROOT/"ornekler/apple_ttm_dcf_assumptions_2026-10-21.json"

def case():
    ttm=calculate_ttm(json.loads(SAMPLE.read_text(encoding="utf-8")),as_of="2026-10-21")
    proposal=json.loads(SCENARIOS.read_text(encoding="utf-8"))
    return ttm,proposal

class HTMLTests(unittest.TestCase):
    def test_financial_values(self):
        t,_=case();h=render_ttm(t)
        self.assertIn("466.82 milyar USD",h)
        self.assertIn("154.86 milyar USD",h)
        self.assertIn("FCFF değildir",h)
        self.assertIn("0000320193-26-000020",h)

    def test_explicit_manual_data_disclosure(self):
        t,_=case()
        h=render_ttm(t)
        self.assertIn("MANUAL_TRANSCRIPTION",h)
        self.assertIn("SEC FY2026 Q3 10-Q",h)

    def test_dcf_scenarios(self):
        t,c=case();v=run_ttm_scenarios(t,c)
        h=render_ttm(t,v)
        self.assertIn("149.46 USD/hisse",h)
        self.assertIn("30.94",h)

    def test_issuer_mismatch_blocks(self):
        t,c=case();v=run_ttm_scenarios(t,c)
        v["cik"]="0000000001"
        with self.assertRaisesRegex(ValueError,"same issuer"):
            render_ttm(t,v)

    def test_html_escape_of_name(self):
        t,_=case();t["company"]="<script>alert(1)</script>"
        h=render_ttm(t)
        self.assertNotIn("<script>alert(1)</script>",h)
        self.assertIn("&lt;script&gt;",h)

    def test_cli_html_writes(self):
        t,_=case()
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"ttm.json";out=Path(root)/"research.html"
            path.write_text(json.dumps(t),encoding="utf-8")
            main(["--ttm",str(path),"--out",str(out)])
            self.assertIn("<!doctype html>",out.read_text(encoding="utf-8"))

if __name__=="__main__":
    unittest.main()
