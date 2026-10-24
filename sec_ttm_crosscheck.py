"""Cross-check two SEC Company Facts TTM engines before trusting a historical baseline.

This audits arithmetic and filing provenance, not authenticity of offline uploads,
investment merit, completeness of the SEC archive, or a DCF prediction.
Python standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path

from sec_companyfacts import SEC_DATA, _validate_cik, download_companyfacts
from sec_ttm import compute_ttm
from ttm_finansallar import CORE, calculate_ttm

VERSION = "ttm-crosscheck-0.1.0"
PROVENANCE_FIELDS = ("start", "end", "filed", "accession", "form", "concept", "value_usd")
COMPONENT_PAIRS = (("annual", "previous_fy"),
                   ("current_ytd9", "current_ytd"),
                   ("prior_ytd9", "prior_ytd"))


def _equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isfinite(a) and math.isfinite(b) and math.isclose(
            a, b, rel_tol=0.0, abs_tol=0.000001)
    return a == b


def audit_ttm(data, *, as_of, expected_cik=None, source_mode="offline_file"):
    """Return a block-by-default, auditable comparison for the same issuer.

    No network request is performed. A 'reconciled' result means *two engines*
    agreed on a supplied JSON snapshot, not that the issuer's data was
    independently authenticated or that any resulting DCF is reliable.
    """
    if source_mode not in ("offline_file", "sec_direct_download"):
        raise ValueError("invalid source mode")
    if not isinstance(data, dict) or not isinstance(data.get("facts"), dict):
        raise ValueError("SEC Company Facts object required")
    cik = _validate_cik(data.get("cik"))
    if expected_cik is not None and _validate_cik(expected_cik) != cik:
        raise ValueError("requested CIK differs from the Company Facts issuer")
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False).encode("utf-8")
    report = {
        "version": VERSION,
        "cik": f"{cik:010d}",
        "company": data.get("entityName"),
        "as_of": as_of,
        "companyfacts_url": SEC_DATA.format(cik=cik),
        "input_mode": source_mode,
        "canonical_json_sha256": hashlib.sha256(canonical).hexdigest(),
        "status": "BLOCKED",
        "historical_baseline_crosschecked": False,
        "automatic_dcf_enabled": False,
        "discrepancies": [],
        "limitations": [
            "A shared data snapshot and two methods do not independently authenticate SEC data",
            "Historical filed-date filtering does not prove the archive was complete as of that date",
            "Only USD US-GAAP Q3 nine-month TTM flows; IFRS/20-F and Q1/Q2 not covered here",
            "CFO minus CapEx is not unlevered FCFF",
            "No verified DCF valuation or investment recommendation",
        ],
    }
    primary = calculate_ttm(data, as_of=as_of)
    report["primary"] = primary
    if primary["status"] != "complete_core":
        report["discrepancies"].append({
            "reason": "PRIMARY_CORE_INCOMPLETE",
            "detail": {k: primary["metrics"][k]["status"] for k in CORE},
        })
        return report

    periods = primary["periods"]
    try:
        secondary = compute_ttm(
            data, as_of=as_of, current_ytd_end=periods["current_9m_end"],
            prior_fy_end=periods["annual_end"], metrics=CORE)
    except ValueError as exc:
        report["discrepancies"].append({
            "reason": "SECONDARY_ENGINE_REJECTED", "detail": str(exc)})
        return report
    report["secondary"] = secondary

    for field, first, second in (
        ("cik", primary["cik"], secondary["cik"]),
        ("as_of", primary["as_of"], secondary["as_of"]),
        ("ttm_end", periods["current_9m_end"], secondary["ttm_end"]),
        ("previous_fy_end", periods["annual_end"], secondary["previous_fy_end"]),
    ):
        if not _equal(first, second):
            report["discrepancies"].append(
                {"reason": "IDENTITY_OR_PERIOD_MISMATCH", "field": field,
                 "primary": first, "secondary": second})

    for metric in CORE:
        a = primary["metrics"][metric]
        b = secondary["metrics"][metric]
        if not _equal(a["value_usd"], b["value_usd"]):
            report["discrepancies"].append({
                "reason": "TTM_VALUE_MISMATCH", "metric": metric,
                "primary": a["value_usd"], "secondary": b["value_usd"]})
        for old_key, new_key in COMPONENT_PAIRS:
            old, new = a[old_key], b["components"][new_key]
            for field in PROVENANCE_FIELDS:
                if not _equal(old.get(field), new.get(field)):
                    report["discrepancies"].append({
                        "reason": "FILING_PROVENANCE_MISMATCH", "metric": metric,
                        "component": old_key, "field": field,
                        "primary": old.get(field), "secondary": new.get(field)})
    if not _equal(primary["cfo_less_capex_usd"], secondary.get("cfo_less_capex_usd")):
        report["discrepancies"].append({"reason": "CFO_MINUS_CAPEX_MISMATCH"})
    if not report["discrepancies"]:
        report["status"] = "RECONCILED_CALCULATIONS"
        report["historical_baseline_crosschecked"] = True
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare independent offline SEC TTM calculations")
    parser.add_argument("--cik", required=True, help="SEC CIK, e.g. 320193 for Apple")
    parser.add_argument("--as-of", required=True, help="YYYY-MM-DD filing knowledge cutoff")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--companyfacts", help="raw SEC Company Facts JSON (offline)")
    source.add_argument("--download", action="store_true",
                        help="one direct SEC request; requires SEC_USER_AGENT")
    parser.add_argument("--snapshot-out", help="save raw downloaded JSON for reproducibility")
    parser.add_argument("--out", required=True, help="cross-check audit JSON")
    options = parser.parse_args(argv)
    if options.snapshot_out and not options.download:
        parser.error("--snapshot-out requires --download")
    cik = _validate_cik(options.cik)
    if options.download:
        raw = download_companyfacts(cik, user_agent=os.getenv("SEC_USER_AGENT", ""))
        source_mode = "sec_direct_download"
        captured_at = dt.datetime.now(dt.timezone.utc).isoformat()
    else:
        raw = json.loads(Path(options.companyfacts).read_text(encoding="utf-8"))
        source_mode = "offline_file"
        captured_at = None
    report = audit_ttm(raw, as_of=options.as_of, expected_cik=cik,
                       source_mode=source_mode)
    if captured_at:
        report["downloaded_at_utc"] = captured_at
    if options.snapshot_out:
        raw_target = Path(options.snapshot_out)
        raw_target.parent.mkdir(parents=True, exist_ok=True)
        raw_target.write_text(json.dumps(raw, ensure_ascii=False, indent=2, allow_nan=False),
                              encoding="utf-8")
        report["snapshot_path"] = str(raw_target)
    target = Path(options.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
                      encoding="utf-8")
    print(f"CIK {report['cik']} | {report['status']} | {target}")
    return 0 if report["historical_baseline_crosschecked"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
