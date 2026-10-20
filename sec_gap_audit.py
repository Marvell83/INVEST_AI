"""Forensic, offline diagnostics for missing SEC annual DCF baselines.

Never substitutes pretax income for operating profit or guesses company facts.
Any detected alias disagreement requires manual reconciliation of a filing.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import pathlib
import zipfile
from collections import Counter

from sec_companyfacts import METRICS, _annual_candidates, _date, normalize_companyfacts

VERSION = "sec-gap-audit-0.1.0"
MAX_JSON_BYTES = 50_000_000


def _latest_end(snapshot, metric):
    return next((r["period_end"] for r in snapshot["annual"]
                 if r["metrics"].get(metric) is not None), None)


def _revenue_disagreements(data, as_of, target_end, threshold=0.05):
    """Find conflicting annual revenue aliases on the SAME fiscal period.

    Different tags may be valid subsets or categories; none is automatically
    relabeled as consolidated revenue. A difference is a REVIEW flag, not proof
    any particular value is wrong.
    """
    if not target_end:
        return []
    values = []
    for alias in METRICS["revenue"]:
        candidate = _annual_candidates(data, alias, _date(as_of)).get(target_end)
        if candidate is not None:
            values.append({"concept": alias, "usd": candidate["value_usd"],
                           "accession": candidate["accession"],
                           "filed": candidate["filed"]})
    if len(values) < 2:
        return []
    max_magnitude = max(abs(r["usd"]) for r in values)
    if max_magnitude == 0:
        return []
    min_value, max_value = min(r["usd"] for r in values), max(r["usd"] for r in values)
    if (max_value - min_value) / max_magnitude > threshold:
        return values
    return []


def audit_company(data, *, as_of):
    normalized = normalize_companyfacts(data, as_of=as_of, years=10)
    latest_any = normalized["annual"][0]["period_end"] if normalized["annual"] else None
    rev_end, ebit_end = (_latest_end(normalized, metric) for metric in ("revenue", "ebit"))
    current = normalized["annual"][0]["metrics"] if normalized["annual"] else {}
    revenue = current.get("revenue")
    ebit = current.get("ebit")
    disagreements = _revenue_disagreements(data, as_of, latest_any)
    if latest_any is None:
        status = "NO_ELIGIBLE_USGAAP_ANNUAL_FACTS"
    elif revenue is None and ebit is None:
        status = "LATEST_REVENUE_AND_EBIT_MISSING"
    elif revenue is None:
        status = "LATEST_REVENUE_MISSING"
    elif ebit is None:
        status = "LATEST_EBIT_MISSING"
    elif disagreements:
        status = "REVENUE_ALIASES_CONFLICT"
    elif revenue["value_usd"] <= 0:
        status = "NONPOSITIVE_REVENUE_BASELINE"
    else:
        status = "READY_FOR_MANUAL_ASSUMPTIONS"
    # EBITDA, profit-before-tax and net income are deliberately not EBIT fallbacks.
    return {
        "cik": normalized["cik"], "company": normalized["company"] or "",
        "status": status, "latest_any_fy_end": latest_any,
        "latest_revenue_fy_end": rev_end, "latest_ebit_fy_end": ebit_end,
        "revenue_usd": revenue["value_usd"] if revenue else None,
        "ebit_usd": ebit["value_usd"] if ebit else None,
        "revenue_concept": revenue["concept"] if revenue else None,
        "revenue_accession": revenue["accession"] if revenue else None,
        "ebit_accession": ebit["accession"] if ebit else None,
        "revenue_alias_disagreements": disagreements,
        "warnings": normalized["warnings"],
        "requires_manual_review": status != "READY_FOR_MANUAL_ASSUMPTIONS",
        "diagnostic_version": VERSION,
    }


def analyze_zip(path, *, as_of, max_files=10000):
    """Process gzipped Company Facts members; no filesystem extraction.

    Limits both compressed archive member size and inflated JSON size.
    """
    _date(as_of)
    records = []
    with zipfile.ZipFile(path) as archive:
        members = sorted((m for m in archive.infolist()
                         if m.filename.startswith("ham_SEC/companyfacts/CIK")
                         and m.filename.endswith(".json.gz")), key=lambda m: m.filename)
        if len(members) > max_files:
            raise ValueError("archive exceeds requested company limit")
        for member in members:
            name = member.filename.rsplit("/", 1)[-1]
            try:
                if member.file_size > MAX_JSON_BYTES:
                    raise ValueError("compressed member size exceeds limit")
                packed = archive.read(member)
                with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:
                    data = stream.read(MAX_JSON_BYTES + 1)
                if len(data) > MAX_JSON_BYTES:
                    raise ValueError("decompressed JSON exceeds size limit")
                facts = json.loads(data)
                result = audit_company(facts, as_of=as_of)
                expected_cik = name.split(".")[0][3:]
                if result["cik"] != expected_cik:
                    raise ValueError("CIK mismatch between filename and Company Facts")
                records.append(result)
            except (ValueError, KeyError, TypeError, json.JSONDecodeError, OSError) as exc:
                records.append({"file": name, "status": "INPUT_ERROR",
                                "error": str(exc), "requires_manual_review": True})
    return records


def export_report(records, csv_path, json_path, *, as_of):
    fields = ("cik", "company", "status", "latest_any_fy_end",
              "latest_revenue_fy_end", "latest_ebit_fy_end",
              "revenue_usd", "ebit_usd", "revenue_concept",
              "revenue_accession", "ebit_accession", "requires_manual_review",
              "warnings", "revenue_alias_disagreements", "error")
    p = pathlib.Path(csv_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in records:
            writer.writerow({**row, "warnings": ";".join(row.get("warnings", [])),
                             "revenue_alias_disagreements": json.dumps(row.get("revenue_alias_disagreements", []), ensure_ascii=False)})
    summary = {"as_of": as_of, "total": len(records),
               "status_counts": dict(sorted(Counter(r["status"] for r in records).items())),
               "requires_manual_review": sum(bool(r["requires_manual_review"]) for r in records),
               "records": records}
    q = pathlib.Path(json_path)
    q.parent.mkdir(parents=True, exist_ok=True)
    q.write_text(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return summary


def main(argv=None):
    p = argparse.ArgumentParser(description="Offline, point-in-time SEC coverage diagnostics")
    p.add_argument("--archive", required=True, help="ZIP of CIK*.json.gz Company Facts")
    p.add_argument("--as-of", required=True, help="YYYY-MM-DD UTC reference date")
    p.add_argument("--csv", required=True)
    p.add_argument("--json", required=True)
    args = p.parse_args(argv)
    records = analyze_zip(args.archive, as_of=args.as_of)
    summary = export_report(records, args.csv, args.json, as_of=args.as_of)
    print(json.dumps({k: v for k, v in summary.items() if k != "records"}, indent=2))


if __name__ == "__main__":
    main()
