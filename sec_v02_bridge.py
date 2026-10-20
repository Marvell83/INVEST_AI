"""Explicit SEC historical baseline to v0.2 DCF with user-sourced assumptions.

No automatic growth, discount rates, net debt, share count, price, or API.
"""
from __future__ import annotations

import argparse
import json
import pathlib

from degerleme_v02 import degerle_v02
from sec_companyfacts import build_dcf_baseline

REQUIRED_ASSUMPTIONS = frozenset((
    "yillar", "buyume", "marj_hedef", "yakinlasma", "satis_sermaye",
    "vergi_orani", "iskonto", "uc_buyume", "uc_roic", "hisse", "net_borc",
))


def _as_string_list(value, field):
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{field} must contain cited source descriptions")
    return value


def value_sec_snapshot(snapshot, proposal):
    """Produce an auditable experimental valuation, refusing missing assumptions.

    Proposal contains:
    * assumptions: all required assumptions except SEC-derived gelir_0/marj_0
    * assumption_sources: list of evidence or explicit analyst scenario sources
    * share_count_source, net_debt_source: nonempty provenance descriptions
    * scenario: optional user-defined scenario name.
    """
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != "sec-companyfacts-0.1.0":
        raise ValueError("unsupported SEC snapshot version")
    if not isinstance(proposal, dict) or not isinstance(proposal.get("assumptions"), dict):
        raise ValueError("proposal requires assumptions object")
    if snapshot.get("unit") != "USD (nominal dollars; not millions)":
        raise ValueError("unsupported monetary units")
    manual = dict(proposal["assumptions"])
    missing = sorted(REQUIRED_ASSUMPTIONS - manual.keys())
    if missing:
        raise ValueError("missing required manual assumptions: " + ", ".join(missing))
    if "gelir_0" in manual or "marj_0" in manual:
        raise ValueError("historical revenue/margin must come from the SEC snapshot, not manual overrides")
    for name in ("share_count_source", "net_debt_source"):
        if not isinstance(proposal.get(name), str) or not proposal[name].strip():
            raise ValueError(f"{name} citation is required")
    assumptions_sources = _as_string_list(proposal.get("assumption_sources"), "assumption_sources")
    baseline = build_dcf_baseline(snapshot)
    if not snapshot["annual"] or baseline["period_end"] != snapshot["annual"][0]["period_end"]:
        raise ValueError("latest SEC period lacks matching annual revenue/EBIT; refusing stale baseline")
    inputs = dict(manual, gelir_0=baseline["gelir_0"], marj_0=baseline["marj_0"])
    valuation = degerle_v02(inputs)
    if valuation["durum"] != "gecerli":
        raise ValueError("DCF engine returned invalid valuation")
    return {
        "status": "experimental_not_investment_advice",
        "issuer": snapshot["company"], "cik": snapshot["cik"],
        "as_of": snapshot["as_of"],
        "historical_period_end": baseline["period_end"],
        "historical_facts": {
            "revenue": baseline["source_revenue"],
            "ebit": baseline["source_ebit"]},
        "manual_assumption_sources": assumptions_sources,
        "share_count_source": proposal["share_count_source"],
        "net_debt_source": proposal["net_debt_source"],
        "scenario": proposal.get("scenario", "base"),
        "inputs": inputs, "valuation": valuation,
        "currency": "USD", "currency_per_share": "USD/share",
        "warnings": list(snapshot.get("warnings", [])) + [
            "Unverified manual assumptions are analyst inputs, not SEC historical facts",
            "No automatic stock split/dilution forecast or share count adjustment",
            "Historical FY ends need not match calendar years; forward row labels are relative years",
            "No discount-rate calibration, margin-growth linkage, or economic predictive validation"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="SEC snapshot to experimental DCF v0.2")
    parser.add_argument("--sec", required=True, help="normalized SEC JSON")
    parser.add_argument("--assumptions", required=True, help="manual proposal JSON")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    with open(args.sec, encoding="utf-8") as src:
        snapshot = json.load(src)
    with open(args.assumptions, encoding="utf-8") as src:
        proposal = json.load(src)
    result = value_sec_snapshot(snapshot, proposal)
    destination = pathlib.Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(f"{result['issuer']}: model {result['valuation']['motor_surumu']} -> {destination}")


if __name__ == "__main__":
    main()
