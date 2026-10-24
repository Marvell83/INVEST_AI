"""Synthetic offline rendering regression tests; no live securities."""
import json
import pathlib
import tempfile
import unittest

from piotroski_fscore import compute_piotroski
from sirket_analiz_paneli import render_dashboard, main
from test_piotroski_coverage_v02 import sample


def quality():
    raw=sample()
    result=compute_piotroski(raw,as_of="2025-03-01",sector="non_financial")
    return {"company":"SYNTHETIC CO","cik":result["cik"],"as_of":"2025-03-01",
            "piotroski":result,"credit":None,"combined_score":None}


def missing_annual_history():
    data=quality();p=data["piotroski"]
    p.update(signals=dict.fromkeys(p["signals"]),known_count=0,missing_count=9,
             score=None,score_range=[0,9],status="partial",
             missing_reasons=dict.fromkeys(p["signals"],"TWO_COMPARABLE_ANNUAL_INCOME_PERIODS_REQUIRED"))
    return data


def dcf():
    return {"cik":"0000000042","status":"recorded_experimental",
            "historical_as_of":"2025-03-01",
            "valuation":{"durum":"gecerli","motor_surumu":"synthetic-v02",
                         "firma_degeri":100000000,"ozsermaye_degeri":80000000,
                         "hisse_basi_deger":15.5,"uc_deger_payi":0.6,"uyarilar":[]}}


class PanelTests(unittest.TestCase):
    def test_partial_piotroski_is_not_full_score(self):
        result=render_dashboard(quality())
        self.assertIn("Tamamlanmadı",result)
        self.assertIn("Olası aralık",result)
        self.assertIn("Tek bileşik puan yok",result)

    def test_experimental_dcf_separate_from_credit_score(self):
        result=render_dashboard(quality(),dcf())
        self.assertIn("80.00 milyon USD",result)
        self.assertIn("synthetic-v02",result)

    def test_other_company_valuation_rejected(self):
        report=dcf();report["cik"]="0000009999"
        with self.assertRaisesRegex(ValueError,"CIK mismatch"):
            render_dashboard(quality(),report)

    def test_script_in_issuer_name_is_escaped(self):
        data=quality();data["company"]='<script>alert("x")</script>'
        result=render_dashboard(data)
        self.assertNotIn("<script>",result)
        self.assertIn("&lt;script&gt;",result)

    def test_untrusted_rating_source_is_not_clickable(self):
        data=quality()
        data["credit"]={"cik":data["cik"],"agency_ratings":{
            "MOODYS":{"rating":"Aa2","outlook":"stable",
                      "investment_grade":True,"published_date":"2025-03-01",
                      "source_url":"javascript:alert(1)"}}}
        result=render_dashboard(data)
        self.assertIn("Kaynak eksik",result)
        self.assertNotIn('href="javascript',result)

    def test_different_data_vintages_warn(self):
        report=dcf();report["historical_as_of"]="2025-02-01"
        self.assertIn("bilgi tarihi ile DCF tarihinin farklı",render_dashboard(quality(),report))

    def test_invalid_piotroski_signal_rejected(self):
        data=quality();data["piotroski"]["signals"]["ROA_POSITIVE"]=7
        with self.assertRaises(ValueError):render_dashboard(data)

    def test_missing_annual_history_is_explained_for_any_issuer(self):
        result=render_dashboard(missing_annual_history())
        self.assertIn("iki karşılaştırılabilir yıllık 10-K net kâr dönemi bulunmuyor",result)
        self.assertIn("Karşılaştırılabilir iki yıllık 10-K net kâr dönemi bulunamadı",result)
        self.assertIn("şirketin finansal kalite puanı değildir",result)
        self.assertNotIn("TWO_COMPARABLE_ANNUAL_INCOME_PERIODS_REQUIRED",result)
        self.assertNotIn("Apple",result)

    def test_annual_history_note_requires_every_signal_blocked(self):
        self.assertNotIn("10-K net kâr dönemi bulunmuyor",render_dashboard(quality()))
        data=missing_annual_history();data["piotroski"]["sector"]="unknown"
        self.assertNotIn("10-K net kâr dönemi bulunmuyor",render_dashboard(data))

    def test_cli_renders_html_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory)
            q=root/"quality.json";v=root/"dcf.json";out=root/"dashboard.html"
            q.write_text(json.dumps(quality()),encoding="utf-8")
            v.write_text(json.dumps(dcf()),encoding="utf-8")
            main(["--quality",str(q),"--valuation",str(v),"--out",str(out)])
            self.assertIn("<!doctype html>",out.read_text(encoding="utf-8"))


if __name__=="__main__":
    unittest.main()
