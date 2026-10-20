"""Evidence-gated resolution for conflicting SEC US-GAAP revenue aliases.

Human must check the 10-K consolidated income statement. This module checks
CIK, annual vintage, matching XBRL amount, SEC accession and source URL.
It does NOT parse SEC filing HTML or authenticate a human's assertion.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import math
import re
from urllib.parse import urlsplit

from sec_companyfacts import METRICS, _annual_candidates, _date
from sec_gap_audit import audit_company

APPROVAL_SCHEMA = "invest-ai-revenue-review-v1"
ACC_PATTERN = re.compile(r"^\d{10}-\d{2}-\d{6}$")


def _filing_url_valid(url, cik, accn):
    if not isinstance(url, str):
        return False
    parts = urlsplit(url)
    expected = f"/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/"
    return (parts.scheme == "https" and parts.hostname == "www.sec.gov"
            and parts.port is None and not parts.username and not parts.password
            and not parts.query and not parts.fragment
            and parts.path.startswith(expected) and len(parts.path) > len(expected)
            and (parts.path.endswith(".htm") or parts.path.endswith(".html")))


def apply_revenue_review(raw_companyfacts, snapshot, *, as_of, review):
    """Return (reviewed snapshot, review receipt) or refuse to proceed.

    Review requires schema_version, status=approved, cik, fiscal_end,
    revenue_concept, value_usd, accession, statement_url, statement_label,
    reviewer, reviewed_at and rationale.
    """
    if not isinstance(review, dict):
        raise ValueError("review object required")
    if review.get("schema_version") != APPROVAL_SCHEMA or review.get("status") != "approved":
        raise ValueError("only explicit versioned human approvals are accepted")
    audit = audit_company(raw_companyfacts, as_of=as_of)
    if audit["status"] != "REVENUE_ALIASES_CONFLICT":
        raise ValueError("a revenue review may only resolve a revenue-label conflict")
    cik, end = audit["cik"], audit["latest_any_fy_end"]
    if review.get("cik") != cik or review.get("fiscal_end") != end:
        raise ValueError("review CIK or fiscal year does not match SEC")
    if snapshot.get("cik") != cik or snapshot.get("as_of") != as_of:
        raise ValueError("normalized snapshot company or vintage mismatch")
    if not snapshot.get("annual") or snapshot["annual"][0]["period_end"] != end:
        raise ValueError("review cannot bypass missing latest fiscal year")
    if snapshot["annual"][0]["metrics"].get("ebit") is None:
        raise ValueError("review cannot bypass missing same-period EBIT")
    concept = review.get("revenue_concept")
    if concept not in METRICS["revenue"]:
        raise ValueError("not an accepted US-GAAP revenue alias")
    candidate = _annual_candidates(raw_companyfacts, concept, _date(as_of)).get(end)
    if candidate is None:
        raise ValueError("reviewed annual fact was not available as-of")
    if review.get("accession") != candidate["accession"] or not ACC_PATTERN.fullmatch(candidate["accession"]):
        raise ValueError("SEC accession mismatch")
    value = review.get("value_usd")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("review value must be finite USD")
    if value <= 0 or abs(float(value) - float(candidate["value_usd"])) > max(0.01, abs(value)*1e-10):
        raise ValueError("review value does not match selected annual XBRL fact")
    if not _filing_url_valid(review.get("statement_url"), cik, candidate["accession"]):
        raise ValueError("SEC 10-K URL CIK/accession mismatch")
    if _date(review.get("reviewed_at")) < _date(candidate["filed"]):
        raise ValueError("review cannot predate SEC filing")
    if _date(review.get("reviewed_at")) > date.today():
        raise ValueError("review date cannot be in the future")
    for field in ("reviewer", "rationale", "statement_label"):
        label = review.get(field)
        if not isinstance(label, str) or len(label.strip()) < (20 if field == "rationale" else 3):
            raise ValueError("missing reviewer attestation: " + field)
    approved = deepcopy(snapshot)
    approved["annual"][0]["metrics"]["revenue"] = deepcopy(candidate)
    approved["selected_us_gaap_concepts"]["revenue"] = concept
    entry = {k: review[k] for k in (
        "schema_version", "status", "cik", "fiscal_end", "revenue_concept",
        "value_usd", "accession", "statement_url", "statement_label",
        "reviewer", "reviewed_at", "rationale")}
    entry["sec_filed"] = candidate["filed"]
    entry["verification_limit"] = ("Verified XBRL candidate/vintage/CIK/accession/URL structure, "
                                   "NOT a cryptographic or automated HTML line verification.")
    approved.setdefault("revenue_reconciliations", []).append(entry)
    approved.setdefault("warnings", []).append("HUMAN_APPROVED_REVENUE_ALIAS_EXCEPTION")
    return approved, entry
