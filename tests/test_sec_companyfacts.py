"""Offline-only synthetic SEC fixtures. No claims about real issuers."""
import copy
import json
import pathlib
import tempfile
import unittest

from sec_companyfacts import (
    _validate_cik, build_dcf_baseline, download_companyfacts,
    main, normalize_companyfacts,
)

BASE = {"cik": 42, "entityName": "SYNTHETIC CO", "facts": {"us-gaap": {}}}


def fact(val, start="2024-01-01", end="2024-12-31", filed="2025-02-15",
         form="10-K", fp="FY", accn="000001-25-000001"):
    return dict(start=start, end=end, val=val, filed=filed,
                form=form, fp=fp, accn=accn)


def fixture():
    data = copy.deepcopy(BASE)
    facts = data["facts"]["us-gaap"]
    for concept, value in (
        ("RevenueFromContractWithCustomerExcludingAssessedTax", 200),
        ("OperatingIncomeLoss", 30),
        ("NetCashProvidedByUsedInOperatingActivities", 40),
        ("PaymentsToAcquirePropertyPlantAndEquipment", 10),
    ):
        facts[concept] = {"units": {"USD": [fact(value)]}}
    return data


class SECNormalizationTests(unittest.TestCase):
    def test_basic_annual_and_source(self):
        record = normalize_companyfacts(fixture(), as_of="2025-03-01")
        row = record["annual"][0]
        self.assertEqual(row["metrics"]["revenue"]["value_usd"], 200)
        self.assertEqual(row["cfo_less_capex_usd"], 30)
        self.assertFalse(row["cfo_less_capex_is_fcff"])
        self.assertEqual(row["metrics"]["ebit"]["accession"], "000001-25-000001")

    def test_asof_blocks_late_filing(self):
        record = normalize_companyfacts(fixture(), as_of="2025-01-01")
        self.assertEqual(record["annual"], [])

    def test_amendment_only_after_publication(self):
        data = fixture()
        rows = data["facts"]["us-gaap"]["OperatingIncomeLoss"]["units"]["USD"]
        rows.append(fact(55, filed="2025-04-01", form="10-K/A", accn="000002"))
        self.assertEqual(
            normalize_companyfacts(data, as_of="2025-03-01")["annual"][0]["metrics"]["ebit"]["value_usd"], 30)
        self.assertEqual(
            normalize_companyfacts(data, as_of="2025-04-02")["annual"][0]["metrics"]["ebit"]["value_usd"], 55)

    def test_quarter_and_8k_excluded(self):
        data = fixture()
        rows = data["facts"]["us-gaap"]["OperatingIncomeLoss"]["units"]["USD"]
        rows.extend([fact(999, start="2024-10-01", form="10-Q", fp="Q4"),
                     fact(888, form="8-K")])
        self.assertEqual(
            normalize_companyfacts(data, as_of="2025-03-01")["annual"][0]["metrics"]["ebit"]["value_usd"], 30)

    def test_same_period_required_for_baseline(self):
        data = fixture()
        data["facts"]["us-gaap"]["OperatingIncomeLoss"]["units"]["USD"] = [
            fact(30, start="2023-01-01", end="2023-12-31", filed="2024-03-01")]
        record = normalize_companyfacts(data, as_of="2025-03-01")
        with self.assertRaises(ValueError):
            build_dcf_baseline(record)

    def test_different_start_date_rejected_in_baseline(self):
        data = fixture()
        data["facts"]["us-gaap"]["OperatingIncomeLoss"]["units"]["USD"] = [
            fact(30, start="2024-01-02")]
        record = normalize_companyfacts(data, as_of="2025-03-01")
        with self.assertRaises(ValueError):
            build_dcf_baseline(record)

    def test_baseline_has_no_guessed_rates_or_shares(self):
        baseline = build_dcf_baseline(
            normalize_companyfacts(fixture(), as_of="2025-03-01"))
        self.assertAlmostEqual(baseline["marj_0"], 0.15)
        self.assertIn("iskonto", baseline["not_provided"])
        self.assertNotIn("hisse", baseline)

    def test_missing_taxonomy_concept_warning(self):
        data = fixture()
        del data["facts"]["us-gaap"]["OperatingIncomeLoss"]
        record = normalize_companyfacts(data, as_of="2025-03-01")
        self.assertIn("MISSING_EBIT", record["warnings"])
        self.assertIsNone(record["annual"][0]["metrics"]["ebit"])

    def test_wrong_unit_not_taken_as_usd(self):
        data = fixture()
        data["facts"]["us-gaap"]["OperatingIncomeLoss"] = {
            "units": {"EUR": [fact(30)]}}
        self.assertIn("MISSING_EBIT", normalize_companyfacts(
            data, as_of="2025-03-01")["warnings"])

    def test_cik_validation(self):
        with self.assertRaises(ValueError):
            _validate_cik("AAPL")
        self.assertEqual(_validate_cik("0000000042"), 42)

    def test_download_rejects_missing_contact_without_network(self):
        with self.assertRaises(ValueError):
            download_companyfacts(42, user_agent="Demo without email")

    def test_cli_offline_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory, "facts.json")
            output = pathlib.Path(directory, "normalized.json")
            source.write_text(json.dumps(fixture()), encoding="utf-8")
            main(["--cik", "42", "--as-of", "2025-03-01",
                  "--file", str(source), "--out", str(output)])
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8"))["cik"], "0000000042")

    def test_wrong_cik_cli_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory, "facts.json")
            source.write_text(json.dumps(fixture()), encoding="utf-8")
            with self.assertRaises(SystemExit):
                main(["--cik", "43", "--as-of", "2025-03-01", "--file",
                      str(source), "--out",
                      str(pathlib.Path(directory, "result.json"))])


if __name__ == "__main__":
    unittest.main()
