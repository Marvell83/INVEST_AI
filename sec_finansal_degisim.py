"""INVEST_AI SEC snapshot-diff and sourced 9M year-over-year observation.

Distinguishes:
  1. changed archive CONTENT, including amendments/comparative re-filings;
  2. same-period TTM revisions when two independent engines reconcile; and
  3. business-period 9M year-over-year arithmetic on the NEW snapshot.
An added comparative fact is not automatically a restatement. 9M YTD growth
is not quarterly, organic, constant-currency or future growth. Stdlib only.
"""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path

from sec_companyfacts import METRICS, _validate_cik
from sec_toplu_tarama import _atomic_write, _canonical_bytes, _iso_date, _load_json
from sec_ttm_crosscheck import audit_ttm

VERSION = "invest-ai-sec-change-0.1.0"
SELECTED = {
    "revenue": METRICS["revenue"],
    "ebit": METRICS["ebit"],
    "cfo": METRICS["cfo"],
    "capex": METRICS["capex"],
    "net_income": ("NetIncomeLoss",),
    "gross_profit": ("GrossProfit",),
}
ALLOWED_FORMS = frozenset(("10-K", "10-K/A", "10-Q", "10-Q/A"))
MAX_OBSERVATIONS = 120000
REPORT_LIMIT = 1000
FORM_FY = frozenset(("10-K", "10-K/A"))


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        return None
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        return None
    return result if result.is_finite() and abs(result) < Decimal("1e30") else None


def _date(value):
    if not isinstance(value, str):
        return None
    try:
        return _iso_date(value)
    except ValueError:
        return None


def _digest(raw):
    return hashlib.sha256(_canonical_bytes(raw)).hexdigest()


def _validated(raw, cik):
    if not isinstance(raw, dict) or not isinstance(raw.get("facts"), dict):
        raise ValueError("raw SEC Company Facts structure is required")
    if _validate_cik(raw.get("cik")) != _validate_cik(cik):
        raise ValueError("CIK mismatch between issuer and source archive")
    return raw


def _view(raw, as_of):
    """Index SEC filings by evidence identity, not merely period end.

    Forms must be annual FY 330-400 days or Q3 9M 240-310 days.
    A duplicate identity with contradictory values blocks the comparison.
    """
    data = raw.get("facts", {}).get("us-gaap", {})
    result = {}
    rows_seen = 0
    for metric, tags in SELECTED.items():
        for concept in tags:
            obs = data.get(concept, {}).get("units", {}).get("USD", [])
            if not isinstance(obs, list):
                continue
            for row in obs:
                if not isinstance(row, dict):
                    continue
                form = row.get("form")
                fp = row.get("fp")
                if form not in ALLOWED_FORMS:
                    continue
                if form in FORM_FY and fp != "FY":
                    continue
                if form not in FORM_FY and fp != "Q3":
                    continue
                start, end, filed = (_date(row.get(k)) for k in ("start", "end", "filed"))
                if not all((start, end, filed)) or end > as_of or filed > as_of or end < start:
                    continue
                from datetime import date
                length = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
                kind = "FY" if form in FORM_FY else "YTD9"
                if not (330 <= length <= 400 if kind == "FY" else 240 <= length <= 310):
                    continue
                val = _number(row.get("val"))
                accn = row.get("accn")
                if val is None or not isinstance(accn, str) or not accn.strip():
                    continue
                key = (metric, concept, kind, start, end, form, fp, filed, accn)
                record = {
                    "metric": metric, "concept": concept, "unit": "USD",
                    "kind": kind, "start": start, "end": end,
                    "form": form, "fp": fp, "filed": filed, "accession": accn,
                    "value_usd": int(val) if val == val.to_integral_value() else float(val),
                }
                if key in result and Decimal(str(result[key]["value_usd"])) != val:
                    raise ValueError("conflicting amounts for same SEC filing identity: " + concept)
                if key not in result:
                    rows_seen += 1
                    if rows_seen > MAX_OBSERVATIONS:
                        raise ValueError("too many relevant SEC observations")
                    result[key] = record
    return result


def _prior_period(new_record, old_view):
    """Prior evidence for exact same concept and start/end, no cross-alias pick."""
    possibilities = [
        v for v in old_view.values()
        if (v["concept"], v["kind"], v["start"], v["end"]) ==
           (new_record["concept"], new_record["kind"], new_record["start"], new_record["end"])
        and (v["filed"], v["accession"]) < (new_record["filed"], new_record["accession"])
    ]
    if not possibilities:
        return None
    return max(possibilities, key=lambda x: (x["filed"], x["accession"]))


def _snapshot_events(old_view, new_view):
    all_keys = sorted(set(old_view) | set(new_view))
    counts = Counter()
    out = []
    candidates = set()
    for key in all_keys:
        old, new = old_view.get(key), new_view.get(key)
        if old is None:
            previous = _prior_period(new, old_view)
            if previous and Decimal(str(previous["value_usd"])) != Decimal(str(new["value_usd"])):
                status = "NEWER_SOURCE_DIFFERENT_AMOUNT_REVIEW"
                candidates.add((new["metric"], new["start"], new["end"], new["concept"]))
            elif new["form"].endswith("/A"):
                status = "AMENDMENT_RECORD_ADDED"
            else:
                status = "FILING_RECORD_ADDED"
            event = {"kind": status, "current": new}
            if previous:
                event["comparable_old_record"] = previous
        elif new is None:
            status = "RECORD_ABSENT_FROM_NEW_SNAPSHOT"
            event = {"kind": status, "previous": old}
        elif _number(new["value_usd"]) != _number(old["value_usd"]):
            status = "SAME_FILING_IDENTITY_VALUE_CHANGED_REVIEW"
            event = {"kind": status, "previous": old, "current": new}
        else:
            continue
        counts[status] += 1
        if len(out) < REPORT_LIMIT:
            out.append(event)
    return {
        "total": sum(counts.values()),
        "by_kind": dict(sorted(counts.items())),
        "events": out,
        "events_truncated": sum(counts.values()) > len(out),
        "events_omitted": sum(counts.values()) - len(out),
        "possible_reported_period_changes": len(candidates),
        "interpretation": (
            "SEC filing identity is concept+period+accession+form+filed. "
            "Added comparative observations or an amended form do NOT establish "
            "an official restatement or explain economic growth. Review issuer filing notes."
        ),
    }


def _safe_audit(raw, *, as_of, cik):
    try:
        result = audit_ttm(raw, as_of=as_of, expected_cik=cik)
    except ValueError as exc:
        return {"status": "UNAVAILABLE_OR_AMBIGUOUS", "historical_baseline_crosschecked": False,
                "discrepancies": [{"reason": "TTM_ENGINE_REFUSED", "detail": str(exc)}]}
    return result


def _percent_change(current, previous):
    # Growth on a nonpositive prior denominator is misleading.
    if previous is None or current is None or previous <= 0:
        return None
    return round((current / previous - 1) * 100, 4)


def _business_trends(ttm):
    if ttm["status"] != "RECONCILED_CALCULATIONS":
        return {"status": "UNAVAILABLE_TTM_NOT_RECONCILED", "items": {},
                "margin": None, "note": "No inferred zero for missing 9M facts"}
    primary = ttm["primary"]
    result = {}
    for metric in ("revenue", "ebit", "cfo", "capex"):
        obj = primary["metrics"][metric]
        cur = obj["current_ytd9"]
        prev = obj["prior_ytd9"]
        from datetime import date
        cur_days = (date.fromisoformat(cur["end"]) - date.fromisoformat(cur["start"])).days + 1
        prev_days = (date.fromisoformat(prev["end"]) - date.fromisoformat(prev["start"])).days + 1
        if abs(cur_days - prev_days) > 7 or not (
                330 <= (date.fromisoformat(cur["end"]) -
                        date.fromisoformat(prev["end"])).days <= 400):
            return {"status": "UNAVAILABLE_INCOMPARABLE_9M_DURATIONS",
                    "items": {}, "margin": None}
        current, prior = (x["value_usd"] for x in (cur, prev))
        result[metric] = {
            "current_ytd9_usd": current, "prior_ytd9_usd": prior,
            "change_usd": current - prior, "change_pct": _percent_change(current, prior),
            "current_source": cur, "prior_source": prev,
            "current_days": cur_days, "prior_days": prev_days,
            "note": "Nine-month YTD same-fiscal-period nominal USD change, NOT standalone Q3",
        }
    rev_now, rev_prior = (result["revenue"][k] for k in
                         ("current_ytd9_usd", "prior_ytd9_usd"))
    ebit_now, ebit_prior = (result["ebit"][k] for k in
                           ("current_ytd9_usd", "prior_ytd9_usd"))
    margin = None
    if rev_now > 0 and rev_prior > 0:
        m1, m0 = (ebit_now / rev_now * 100, ebit_prior / rev_prior * 100)
        margin = {
            "current_operating_margin_pct": round(m1, 4),
            "prior_operating_margin_pct": round(m0, 4),
            "change_percentage_points": round(m1-m0, 4),
            "note": "Operating margin measured for comparable 9M YTD periods only",
        }
    return {"status": "AVAILABLE_9M_YOY", "items": result, "margin": margin,
            "as_of": primary["as_of"], "current_9m_end": primary["periods"]["current_9m_end"],
            "prior_9m_end": primary["periods"]["prior_9m_end"]}


def _same_period_ttm(old_ttm, new_ttm):
    if (old_ttm["status"] != "RECONCILED_CALCULATIONS" or
            new_ttm["status"] != "RECONCILED_CALCULATIONS"):
        return {"status": "UNAVAILABLE_UNRECONCILED", "metrics": {}}
    old = old_ttm["primary"]
    new = new_ttm["primary"]
    if old["periods"] != new["periods"]:
        return {"status": "DIFFERENT_PERIODS_NO_DIRECT_COMPARISON",
                "old_periods": old["periods"], "new_periods": new["periods"],
                "metrics": {}}
    amounts = {}
    for m in ("revenue", "ebit", "cfo", "capex"):
        a, b = (r["metrics"][m]["value_usd"] for r in (old, new))
        amounts[m] = {
            "old_usd": a, "new_usd": b, "change_usd": b-a,
            "change_pct": _percent_change(b, a),
            "classification": "SAME_PERIOD_ARCHIVE_VALUE_DIFFERENCE_NOT_BUSINESS_GROWTH",
        }
    return {"status": "SAME_PERIOD_RECONCILED", "periods": new["periods"],
            "metrics": amounts}


def compare_sec_snapshots(old, new, *, as_of, expected_cik):
    """Strict, deterministic same-cutoff delta between TWO issuer captures.

    Snapshot order is supplied by caller: timestamps cannot be inferred from
    content hashes or filing years. Stored index.json tracks only latest capture.
    """
    as_of = _iso_date(as_of)
    cik = f"{_validate_cik(expected_cik):010d}"
    _validated(old, cik)
    _validated(new, cik)
    before = _view(old, as_of)
    after = _view(new, as_of)
    events = _snapshot_events(before, after)
    old_audit = _safe_audit(old, as_of=as_of, cik=cik)
    new_audit = _safe_audit(new, as_of=as_of, cik=cik)
    concerns = []
    for reason in ("NEWER_SOURCE_DIFFERENT_AMOUNT_REVIEW",
                   "SAME_FILING_IDENTITY_VALUE_CHANGED_REVIEW",
                   "RECORD_ABSENT_FROM_NEW_SNAPSHOT",
                   "AMENDMENT_RECORD_ADDED"):
        if events["by_kind"].get(reason, 0):
            concerns.append(reason)
    if old_audit["status"] != "RECONCILED_CALCULATIONS":
        concerns.append("OLDER_TTM_UNRECONCILED")
    if new_audit["status"] != "RECONCILED_CALCULATIONS":
        concerns.append("NEW_TTM_UNRECONCILED")
    old_hash, new_hash = _digest(old), _digest(new)
    def is_transcribed(data):
        notes = data.get("evidence_notes")
        status = str(notes.get("status", "")).upper() if isinstance(notes, dict) else ""
        return "MANUAL" in status or "TRANSCRIPTION" in status
    manual_old, manual_new = is_transcribed(old), is_transcribed(new)
    if manual_old or manual_new:
        concerns.append("MANUALLY_TRANSCRIBED_NOT_RAW_SEC_API")
    return {
        "version": VERSION, "cik": cik, "company": new.get("entityName"),
        "old_source_manual_transcription": manual_old,
        "new_source_manual_transcription": manual_new,
        "as_of": as_of,
        "snapshot_order": "CALLER_SUPPLIED_OLD_THEN_NEW_NOT_VERIFIED_BY_THIS_MODULE",
        "old_snapshot_sha256": old_hash, "new_snapshot_sha256": new_hash,
        "identical_snapshots": old_hash == new_hash,
        "focused_on": "USD US-GAAP annual FY and Q3 9M YTD SEC Company Facts observations",
        "observations": {"old": len(before), "new": len(after)},
        "snapshot_record_changes": events,
        "old_ttm_status": old_audit["status"],
        "new_ttm_status": new_audit["status"],
        "same_period_ttm_reconciliation": _same_period_ttm(old_audit, new_audit),
        "new_snapshot_9m_yoy": _business_trends(new_audit),
        "requires_manual_review": bool(concerns),
        "review_reasons": concerns,
        "investment_recommendation": None, "forecast": None, "price_target": None,
        "limitations": [
            "Snapshot comparison is NOT an issuer-authorized restatement determination.",
            "Caller must supply true chronological snapshots; hashes do not encode capture time.",
            "Same-period revision != financial growth. 9M YoY != quarterly growth.",
            "Two audit engines share one input; agreement is not independent SEC authenticity verification.",
            "Both snapshots use the same as_of cutoff; absence/presence does not prove historical archive completeness.",
            "IFRS/20-F, bank-specific metrics, new quarter stand-alone Q1/Q2 and share-based accounting not covered.",
            "No real-time quote, investing advice or quantitative prediction.",
        ],
    }


def _load_snapshot(path, expected_cik):
    """Read 50 MB at most and verify content-addressed batch archive filenames."""
    data = _load_json(path, max_bytes=50_000_000)
    _validated(data, expected_cik)
    name = Path(path).stem
    if len(name) == 64 and all(c in "0123456789abcdef" for c in name):
        if name != _digest(data):
            raise ValueError("archive filename SHA-256 mismatch")
    return data


def main(argv=None):
    p = argparse.ArgumentParser(description="INVEST_AI source-audited SEC change detector")
    p.add_argument("--old", required=True, help="historically EARLIER Company Facts archive")
    p.add_argument("--new", required=True, help="historically LATER Company Facts archive")
    p.add_argument("--cik", required=True)
    p.add_argument("--as-of", required=True, help="same filed-date cutoff for both files")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    paths = [Path(x).resolve() for x in (args.old, args.new, args.out)]
    if len(set(paths)) != 3:
        p.error("old, new and output paths must be distinct")
    old, new = (_load_snapshot(path, args.cik) for path in (args.old, args.new))
    report = compare_sec_snapshots(old, new, as_of=args.as_of, expected_cik=args.cik)
    _atomic_write(args.out, json.dumps(report, indent=2, ensure_ascii=False,
                                     allow_nan=False).encode("utf-8"))
    print(f"CIK {report['cik']} | {report['snapshot_record_changes']['total']} SEC fact events"
          f" | 9M YoY {report['new_snapshot_9m_yoy']['status']} | {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
