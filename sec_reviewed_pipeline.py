"""Strict SEC Company Facts -> experimental DCF v0.2 -> forecast ledger.

Use raw Company Facts so conflicting revenue tags can be detected before
valuation. An analyst supplies *all* forward assumptions and future FY ends.
No market price, automatic forecasts, or FCFF-from-CFO shortcut.
"""
from __future__ import annotations

import datetime as dt
import math

from sec_companyfacts import normalize_companyfacts
from sec_gap_audit import audit_company
from sec_revenue_reconciliation import apply_revenue_review
from sec_v02_bridge import value_sec_snapshot
from tahmin_defteri import TahminDefteri

PIPELINE_VERSION = "sec-reviewed-ledger-0.1.0"
FORECAST_METRICS = (("revenue", "gelir"), ("ebit", "ebit"), ("fcff", "fcff"))


def _validate_periods(periods, *, baseline_end, years):
    """No fake December-31 convention: user must provide projected FY end dates."""
    if not isinstance(periods, list) or len(periods) != years:
        raise ValueError("future_period_ends: one explicit fiscal end per projected year required")
    try:
        previous = dt.date.fromisoformat(baseline_end)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid historic fiscal period end") from exc
    for item in periods:
        if not isinstance(item, str):
            raise ValueError("each fiscal end must be an ISO date string")
        try:
            current = dt.date.fromisoformat(item)
        except ValueError as exc:
            raise ValueError("invalid future fiscal end") from exc
        if not 330 <= (current - previous).days <= 400:
            raise ValueError("future fiscal periods must follow one another by 330..400 days")
        previous = current


def analyze_and_record(*, raw_companyfacts, as_of, proposal,
                       future_period_ends, db_path, revenue_review=None):
    """Returns valuation, CIK, source audit and ledger row IDs.

    Refuses incomplete/contradictory historic inputs; does not silently repair.
    All batch writes belong to one SQLite transaction, or none persist.
    """
    audit = audit_company(raw_companyfacts, as_of=as_of)
    snapshot = normalize_companyfacts(raw_companyfacts, as_of=as_of)
    reconciliation = None
    if audit["status"] == "REVENUE_ALIASES_CONFLICT" and revenue_review is not None:
        snapshot, reconciliation = apply_revenue_review(
            raw_companyfacts, snapshot, as_of=as_of, review=revenue_review)
    elif audit["status"] != "READY_FOR_MANUAL_ASSUMPTIONS":
        raise ValueError("SEC baseline requires manual review: " + audit["status"])
    elif revenue_review is not None:
        raise ValueError("revenue review cannot override an uncontested baseline")
    valued = value_sec_snapshot(snapshot, proposal)
    forecasts = valued["valuation"]["tablo"]
    _validate_periods(future_period_ends, baseline_end=valued["historical_period_end"],
                      years=len(forecasts))
    sources = [
        "SEC Company Facts: " + snapshot["source_url"],
        "SEC revenue accession: " + valued["historical_facts"]["revenue"]["accession"],
        "SEC EBIT accession: " + valued["historical_facts"]["ebit"]["accession"],
        "Share count: " + valued["share_count_source"],
        "Net debt: " + valued["net_debt_source"],
        *valued["manual_assumption_sources"],
        *(["SEC revenue reconciliation: " + reconciliation["statement_url"]]
          if reconciliation is not None else []),
    ]
    # Distinguish date of source availability (as_of) from the date the model
    # was actually run. Historic as-of data alone do not prove an old prediction.
    assumptions = {
        "pipeline_version": PIPELINE_VERSION,
        "historic_as_of": as_of,
        "historic_fy_end": valued["historical_period_end"],
        "historic_facts": valued["historical_facts"],
        "manual_sources": valued["manual_assumption_sources"],
        "net_debt_source": valued["net_debt_source"],
        "share_count_source": valued["share_count_source"],
        "scenario": valued["scenario"],
        "inputs": valued["inputs"],
        "valuation_summary": {k: valued["valuation"][k]
                              for k in ("firma_degeri", "ozsermaye_degeri", "hisse_basi_deger", "uc_deger_payi")},
        "historical_prediction_verifiable": False,
        "revenue_reconciliation": reconciliation,
    }
    ids = []
    with TahminDefteri(db_path) as ledger:
        ledger.db.execute("BEGIN IMMEDIATE")
        try:
            for row, target in zip(forecasts, future_period_ends):
                for metric, source_field in FORECAST_METRICS:
                    value = float(row[source_field])
                    if not math.isfinite(value):
                        raise ValueError("nonfinite forecast")
                    ids.append(ledger.tahmin_kaydet(
                        company="CIK:" + snapshot["cik"],
                        metric=metric, target_period="FY_END:" + target,
                        currency="USD", predicted=value,
                        model_version=valued["valuation"]["motor_surumu"],
                        assumptions=assumptions, sources=sources))
            ledger.db.commit()
        except Exception:
            ledger.db.rollback()
            raise
    return {
        "status": "recorded_experimental",
        "issuer": valued["issuer"], "cik": valued["cik"],
        "historical_as_of": as_of,
        "forecast_rows": len(ids), "forecast_ids": ids,
        "valuation": valued["valuation"], "sec_audit": audit,
        "revenue_reconciliation": reconciliation,
        "warning": "Created now, not a verifiable prediction made at historical as-of date; do not score FCFF against CFO less CapEx",
    }
