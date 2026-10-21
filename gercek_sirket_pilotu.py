"""INVEST_AI: offline evidence-first company pilot from raw SEC Company Facts.

Creates an auditable Piotroski / issuer-credit / *optional external* DCF report.
No market quote, issuer credit grade, SBC conclusions, equity offering evidence,
or future projections are inferred. The DCF panel is intentionally empty.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import pathlib

from kredi_notlari import company_quality_snapshot
from sec_companyfacts import _validate_cik
from sirket_analiz_paneli import render_dashboard

VERSION = "invest-ai-real-sec-pilot-0.1.0"
SOURCE_DESCRIPTION = (
    "Offline raw SEC Company Facts snapshot. A knowledge cutoff is not evidence "
    "that the archive captures every filing available on that day."
)

# Restrict to human-legible standard monetary data, never invent totals.
FACTS = (
    ("ni_t", "net_income_t", "Net income"),
    ("cfo_t", "cfo_t", "Operating cash flow"),
    ("rev_t", "revenue_t", "Revenue"),
    ("gp_t", "gross_profit_t", "Gross profit"),
    ("a_t", "assets_t", "Total assets"),
    ("d_t", "debt_t", "Long-term noncurrent debt"),
    ("ca_t", "ca_t", "Current assets"),
    ("cl_t", "cl_t", "Current liabilities"),
)


def _iso(value):
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("as_of must be ISO YYYY-MM-DD") from exc


def _safe(value):
    return html.escape(str(value), quote=True)


def _fmt_millions(value):
    if not isinstance(value, (float, int)) or isinstance(value, bool):
        return "—"
    return f"{value / 1_000_000:,.1f} million USD"


def build_pilot(raw_companyfacts, *, as_of, expected_cik,
                expected_fiscal_end=None, sector="unknown", credit_db=None,
                equity_offering_evidence=None, source_sha256=None,
                snapshot_note="historical local archive"):
    """Build self-contained HTML + JSON results, without auto-valuing stock."""
    _iso(as_of)
    if sector != "non_financial":
        raise ValueError("pilot requires a confirmed non_financial sector; sector-specific method otherwise required")
    cik = f"{_validate_cik(raw_companyfacts.get('cik')):010d}"
    expected = f"{_validate_cik(expected_cik):010d}"
    if expected != cik:
        raise ValueError("CIK mismatch: data and requested issuer differ")
    quality = company_quality_snapshot(
        raw_companyfacts, as_of=as_of, sector=sector,
        equity_offering_evidence=equity_offering_evidence, credit_db=credit_db)
    p = quality["piotroski"]
    end = p.get("periods", {}).get("current_fy_end")
    if expected_fiscal_end is not None and end != expected_fiscal_end:
        raise ValueError("latest reported fiscal period does not match expected period")
    if not end or not p.get("periods", {}).get("prior_fy_end"):
        raise ValueError("no point-in-time comparable annual SEC income statements")
    if _iso(end) > _iso(as_of):
        raise ValueError("future annual financial period in output")
    records = []
    for key, fallback_key, label in FACTS:
        fact = p.get("provenance", {}).get(key) or p.get("provenance", {}).get(fallback_key)
        if fact is None:
            continue
        if _iso(fact["filed"]) > _iso(as_of):
            raise ValueError("source fact published after research knowledge cutoff")
        records.append({
            "key": key, "label": label, "concept": fact["concept"],
            "usd": fact["value_usd"], "period_end": fact["end"],
            "filed": fact["filed"], "accession": fact["accession"],
            "source": fact["source"],
            "method": fact.get("method", "DIRECT_XBRL"),
            "derivation": fact.get("derivation"),
        })
    report = {
        "pipeline_version": VERSION,
        "company": quality["company"], "cik": cik,
        "knowledge_cutoff": as_of, "latest_fiscal_end": end,
        "source_snapshot_sha256": source_sha256,
        "source_snapshot_note": snapshot_note,
        "source_limitations": SOURCE_DESCRIPTION,
        "official_issuer_credit_rating_verified": False,
        "real_company_report": True,
        "actual_stock_price": None,
        "dcf_result": None,
        "not_retroactive_forecast": True,
        "quality": quality,
        "key_facts": records,
        "methodology_warnings": [
            "Nonfinancial industry assumption must be checked against SEC industry registration.",
            "Equity issuance requires a dated human-reviewed source, not raw share-count changes.",
            "An unknown F-Score component must not be treated as zero.",
            "No DCF fair value, reverse DCF implied growth, stock return, or credit rating is inferred.",
            "This report is generated from a frozen SEC archive, not a live SEC reconciliation.",
        ],
    }
    view = render_dashboard(quality)
    rows = "".join(
        "<tr>" + "".join(f"<td>{_safe(v)}</td>" for v in (
            x["label"], _fmt_millions(x["usd"]), x["concept"],
            x["period_end"], x["filed"], x["accession"], x["method"])) + "</tr>"
        for x in records)
    section = f"""
    <section class='card'><h2>Gerçek SEC kanıtları — kaynak izi</h2>
    <p>Bu alan değerleme tahmini değildir. SEC finansal olgularının
    yayımlanma tarihlerini ve muhasebe kavramlarını gösterir.</p>
    <p>Ham veri SHA-256: <code>{_safe(source_sha256 or 'Not supplied')}</code></p>
    <p>Arşiv açıklaması: {_safe(snapshot_note)}</p>
    <div class='scroll'><table><thead><tr><th>Finansal kalem</th><th>USD</th>
    <th>XBRL kavramı</th><th>Mali dönem</th><th>Yayım</th><th>Accession</th><th>Yöntem</th></tr></thead>
    <tbody>{rows}</tbody></table></div>
    <p>As-of filtresi gelecekte yayımlanmış olguları dışlar; fakat
    eski bir arşivin tüm bilgilere sahip olduğunu kanıtlamaz.</p></section>
    """
    if "</main>" not in view:
        raise ValueError("dashboard HTML closing marker not found")
    view = view.replace("</main>", section + "</main>", 1)
    return report, view


def main(argv=None):
    parser = argparse.ArgumentParser(description="INVEST_AI actual SEC historical-quality pilot")
    parser.add_argument("--companyfacts", required=True, help="offline raw SEC JSON")
    parser.add_argument("--as-of", required=True, help="ISO research knowledge cutoff")
    parser.add_argument("--expected-cik", required=True, help="fail on different company")
    parser.add_argument("--sector", choices=("non_financial","financial","unknown"), required=True)
    parser.add_argument("--expected-fiscal-end", required=True, help="fail on stale/future fiscal baseline")
    parser.add_argument("--snapshot-note", default="SEC raw Company Facts saved locally")
    parser.add_argument("--ratings-db", help="optional manually curated issuer ratings SQLite")
    parser.add_argument("--equity-evidence", help="optional dated, human-approved share-issuance evidence JSON")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-html", required=True)
    opts = parser.parse_args(argv)
    src = pathlib.Path(opts.companyfacts)
    raw_bytes = src.read_bytes()
    data = json.loads(raw_bytes)
    evidence = json.loads(pathlib.Path(opts.equity_evidence).read_text(encoding="utf-8")) if opts.equity_evidence else None
    report, page = build_pilot(data, as_of=opts.as_of, expected_cik=opts.expected_cik,
                              expected_fiscal_end=opts.expected_fiscal_end, sector=opts.sector,
                              credit_db=opts.ratings_db, equity_offering_evidence=evidence,
                              source_sha256=hashlib.sha256(raw_bytes).hexdigest(),
                              snapshot_note=opts.snapshot_note)
    dest_json = pathlib.Path(opts.out_json)
    dest_html = pathlib.Path(opts.out_html)
    for d in (dest_json, dest_html):
        d.parent.mkdir(parents=True, exist_ok=True)
    dest_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    dest_html.write_text(page, encoding="utf-8")
    print(report["company"], report["latest_fiscal_end"],
          "Piotroski", report["quality"]["piotroski"]["score_range"],
          "(complete:", report["quality"]["piotroski"]["score"] is not None, ")")
    print("Outputs:", dest_json, dest_html)


if __name__ == "__main__":
    main()