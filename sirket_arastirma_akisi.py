"""Evidence-first, one-command SEC company research orchestration.

Independent, previously tested components are composed without overriding their
methodologies. Missing Piotroski/TTM data remains missing. No prices, DCF,
automatic forecasts, trading signals, or subscription services.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
from pathlib import Path
import re

from finansal_oranlar import compute_ratios
from finansal_tablolar import build_annual_statements, build_quarterly_statements
from kredi_notlari import company_quality_snapshot
from sec_companyfacts import SEC_DATA, _validate_cik, download_companyfacts
from sec_gap_audit import audit_company
from sec_ttm_crosscheck import audit_ttm
from sirket_analiz_paneli import render_dashboard, render_financial_sections, render_quarterly_section

VERSION = "invest-ai-company-research-0.1.0"
SECTORS = ("non_financial", "financial", "unknown")
INPUT_MODES = ("offline_file", "sec_direct_download")
NO_ANNUAL_ERROR = "no eligible USD annual 10-K data by cutoff"


def _safe(value):
    return html.escape(str(value), quote=True)


def _date(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(field + ": ISO YYYY-MM-DD required")
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(field + ": invalid calendar date") from exc
    return value


def _canonical_digest(raw):
    content = json.dumps(raw, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def build_company_research(raw, *, as_of, expected_cik, sector,
                           credit_db=None, equity_offering_evidence=None,
                           expected_fiscal_end=None, input_mode="offline_file"):
    """Return one issuer's dated annual, Piotroski and TTM evidence.

    Sector and CIK are explicit analyst inputs, not inferred from the ticker.
    A complete component means its *math and eligibility checks* passed, not
    that its SEC values or issuer sector were independently authenticated.
    """
    _date(as_of, "as_of")
    if input_mode not in INPUT_MODES:
        raise ValueError("invalid input_mode")
    if sector not in SECTORS:
        raise ValueError("sector must be non_financial, financial or unknown")
    if not isinstance(raw, dict) or not isinstance(raw.get("facts"), dict):
        raise ValueError("raw SEC Company Facts object required")
    cik = f"{_validate_cik(raw.get('cik')):010d}"
    if cik != f"{_validate_cik(expected_cik):010d}":
        raise ValueError("requested CIK differs from SEC Company Facts CIK")
    if expected_fiscal_end is not None:
        _date(expected_fiscal_end, "expected_fiscal_end")
    if credit_db is not None and not Path(credit_db).is_file():
        raise ValueError("ratings database does not exist")

    annual = audit_company(raw, as_of=as_of)
    quality = company_quality_snapshot(
        raw, as_of=as_of, sector=sector, credit_db=credit_db,
        equity_offering_evidence=equity_offering_evidence)
    if annual["cik"] != cik or quality["cik"] != cik or quality["piotroski"]["cik"] != cik:
        raise ValueError("issuer mismatch between research components")

    if expected_fiscal_end is not None and annual["latest_any_fy_end"] != expected_fiscal_end:
        raise ValueError("annual fiscal year is missing or differs from expected_fiscal_end")

    try:
        ttm = audit_ttm(raw, as_of=as_of, expected_cik=cik, source_mode=input_mode)
    except ValueError as exc:
        if str(exc) != NO_ANNUAL_ERROR:
            raise
        ttm = {
            "status": "UNAVAILABLE_NO_ELIGIBLE_ANNUAL_DATA",
            "historical_baseline_crosschecked": False,
            "discrepancies": [{"reason": "MISSING_ANNUAL_BASIS", "detail": str(exc)}],
        }
    if ttm.get("cik") not in (None, cik):
        raise ValueError("TTM issuer differs from requested CIK")
    statements = build_annual_statements(raw, as_of=as_of)
    quarterly = build_quarterly_statements(raw, as_of=as_of)
    if statements["cik"] != cik or quarterly["cik"] != cik:
        raise ValueError("financial statements issuer differs from requested CIK")
    ratios = compute_ratios(statements)

    p = quality["piotroski"]
    gaps = []
    if annual["status"] != "READY_FOR_MANUAL_ASSUMPTIONS":
        gaps.append("ANNUAL_SOURCE_REVIEW_REQUIRED:" + annual["status"])
    if sector != "non_financial":
        gaps.append("SECTOR_SPECIFIC_PIOTROSKI_UNAVAILABLE")
    elif p["score"] is None:
        gaps.append("PIOTROSKI_INCOMPLETE:" + str(p["known_count"]) + "/9")
    if ttm["status"] != "RECONCILED_CALCULATIONS":
        gaps.append("TTM_NOT_RECONCILED:" + ttm["status"])
    annual_end = annual.get("latest_any_fy_end")
    p_end = p.get("periods", {}).get("current_fy_end")
    if annual_end and p_end and p_end != annual_end:
        gaps.append("PIOTROSKI_ANNUAL_PERIOD_MISMATCH")
    if ttm.get("primary", {}).get("periods", {}).get("annual_end") not in (None, annual_end):
        gaps.append("TTM_ANNUAL_PERIOD_MISMATCH")

    evidence = raw.get("evidence_notes")
    manual = isinstance(evidence, dict) and (
        "MANUAL" in str(evidence.get("status", "")).upper() or
        "TRANSCRIPTION" in str(evidence.get("status", "")).upper())
    if manual:
        gaps.append("INPUT_IS_MANUAL_TRANSCRIPTION_NOT_RAW_SEC_DOWNLOAD")
    if input_mode == "offline_file":
        gaps.append("OFFLINE_DATA_AUTHENTICITY_NOT_INDEPENDENTLY_VERIFIED")
    # Never elevate a shared snapshot to an independently verified SEC filing.
    limitations = [
        "Source authenticity and complete historical SEC coverage are not independently verified.",
        "An as_of cutoff prevents using later-filed facts present in this snapshot; it does not prove archive completeness.",
        "Annual screening eligibility does not authenticate consolidated accounting labels.",
        "Piotroski F-Score, issuer credit ratings and TTM are distinct views, never combined into a stock score.",
        "Credit ratings require separately maintained source-cited manual observations.",
        "TTM flow arithmetic is not a future cash-flow forecast; CFO minus CapEx is not unlevered FCFF.",
        "No automatic DCF, discount rate, market price, price target, stock ranking or buy/sell recommendation.",
        "IFRS/20-F, finance-sector-specific scoring and Q1/Q2 TTM need dedicated methodologies.",
        "Annual statements cover selected US-GAAP line items; lease liabilities, marketable securities "
        "and segment data are not included, and historical ratios are not forecasts.",
    ]
    complete = not gaps
    return {
        "version": VERSION,
        "cik": cik, "company": raw.get("entityName", ""),
        "as_of": as_of, "sector_assumption": sector,
        "source": {
            "mode": input_mode,
            "companyfacts_url": SEC_DATA.format(cik=int(cik)),
            "canonical_json_sha256": _canonical_digest(raw),
            "origin_verified_independently": False,
            "manually_transcribed_source": manual,
            "evidence_notes": evidence,
        },
        "coverage_status": "ELIGIBLE_COMPONENT_MATH_COMPLETE" if complete else "PARTIAL_OR_REVIEW_REQUIRED",
        "research_gaps": gaps,
        "annual_source_audit": annual,
        "quality": quality,
        "ttm_crosscheck": ttm,
        "financial_statements": statements,
        "financial_ratios": ratios,
        "quarterly_statements": quarterly,
        "actual_price": None, "dcf": None, "combined_investment_score": None,
        "forecast_created": False, "investment_recommendation": None,
        "limitations": limitations,
    }


def render_company_research(report):
    if not isinstance(report, dict) or report.get("version") != VERSION:
        raise ValueError("supported INVEST_AI company research report required")
    quality = report.get("quality")
    if not isinstance(quality, dict) or quality.get("cik") != report.get("cik"):
        raise ValueError("issuer mismatch in research report")
    base = render_dashboard(quality)
    annual = report["annual_source_audit"]
    ttm = report["ttm_crosscheck"]
    gaps = report["research_gaps"]
    intro = (
        "<section class='card'><h2>SEC kaynak kapsama denetimi</h2>"
        "<p>Son yıllık dönem: <strong>" + _safe(annual.get("latest_any_fy_end") or "Bilinmiyor") +
        "</strong> · Yıllık inceleme durumu: <strong>" + _safe(annual["status"]) + "</strong></p>"
        "<p>Gelir kaydı: " + _safe(annual.get("revenue_concept") or "Eksik") +
        " · SEC accession: " + _safe(annual.get("revenue_accession") or "Eksik") + "</p>"
        "<p>Faaliyet kârı accession: " + _safe(annual.get("ebit_accession") or "Eksik") + "</p>"
        "<p>Girdi: " + _safe(report["source"]["mode"]) + "</p>"
        "<p>JSON içerik SHA-256: <code>" +
        _safe(report["source"]["canonical_json_sha256"]) + "</code></p>"
        "<p class='muted'>Bu hash veri bütünlüğü karşılaştırmasına yarar, SEC dijital imzası değildir.</p>"
        "<p class='muted'>Bu yıllık inceleme durumu gelir ve faaliyet kârı kaydının kontrolüdür; "
        "Piotroski için iki karşılaştırılabilir yıllık dönem ve ilgili bilanço geçmişi "
        "ayrıca gerekir. TTM mutabakatı tek başına Piotroski'yi tamamlamaz.</p></section>"
    )
    if ttm["status"] == "RECONCILED_CALCULATIONS":
        primary = ttm["primary"]
        ttm_rows = []
        for label, name in (("Gelir", "revenue"), ("Faaliyet kârı", "ebit"),
                            ("Faaliyet nakit akışı", "cfo"), ("CapEx", "capex")):
            item = primary["metrics"][name]
            ttm_rows.append("<tr><td>" + _safe(label) + "</td><td>" +
                            _safe(f"{item['value_usd']:,.0f} USD") + "</td><td>" +
                            _safe(item["annual"]["accession"]) + "</td><td>" +
                            _safe(item["current_ytd9"]["accession"]) + "</td></tr>")
        ttm_section = (
            "<section class='card'><h2>TTM — kaynakları karşılaştırılmış finansallar</h2>"
            "<p>12 aylık bitiş: " + _safe(primary["periods"]["current_9m_end"]) + "</p>"
            "<div class='scroll'><table><thead><tr><th>Kalem</th><th>TTM</th>"
            "<th>Önceki yıl 10-K</th><th>Güncel 10-Q</th></tr></thead><tbody>" +
            "".join(ttm_rows) + "</tbody></table></div>"
            "<p class='muted'>İki hesap motorunun dönem ve accession mutabakatı geçildi. "
            "Aynı girdi dosyasına dayandığı için bağımsız SEC kaynak onayı değildir. "
            "CFO−CapEx, FCFF değildir.</p></section>"
        )
    else:
        discrepancy = ", ".join(x.get("reason", "UNKNOWN") for x in ttm.get("discrepancies", []))
        ttm_section = (
            "<section class='card'><h2>TTM finansalları — mutabakat bekliyor</h2>"
            "<p>Durum: <strong>" + _safe(ttm["status"]) + "</strong></p>"
            "<p>Gerekçeler: " + _safe(discrepancy or "Kullanılabilir kaynak bulunamadı") + "</p>"
            "<p class='muted'>Eksik veriler yerine tutar veya değerleme üretilmedi.</p></section>"
        )
    details = "".join("<li>" + _safe(x) + "</li>" for x in gaps) or (
        "<li>Hesap motorlarının tanımlı kapsama şartları karşılandı; kaynak bağımsız doğrulanmış değildir.</li>")
    limits = "".join("<li>" + _safe(x) + "</li>" for x in report["limitations"])
    notes = (
        "<section class='card'><h2>Açık veri eksikleri</h2><ul>" + details + "</ul></section>"
        "<section class='card'><h2>Araştırmanın sınırları</h2><ul>" + limits +
        "</ul><p>Hedef fiyat, şirket sıralaması ve otomatik al/sat sinyali üretilmez.</p></section>"
    )
    if "</main>" not in base:
        raise ValueError("dashboard closing marker missing")
    financials = ""
    if "financial_statements" in report:
        financials = render_financial_sections(report["financial_statements"], report["financial_ratios"])
    if "quarterly_statements" in report:
        financials += render_quarterly_section(report["quarterly_statements"])
    return base.replace("</main>", intro + financials + ttm_section + notes + "</main>", 1)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="INVEST_AI one-command, evidence-first SEC company research")
    parser.add_argument("--cik", required=True, help="SEC issuer CIK")
    parser.add_argument("--as-of", required=True, help="research knowledge cutoff YYYY-MM-DD")
    parser.add_argument("--sector", required=True, choices=SECTORS,
                        help="explicit analyst classification, not guessed by system")
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--companyfacts", help="local raw SEC Company Facts JSON")
    input_group.add_argument("--download", action="store_true",
                             help="one SEC Company Facts request; SEC_USER_AGENT required")
    parser.add_argument("--snapshot-out", help="required when --download")
    parser.add_argument("--ratings-db", help="existing manual issuer-rating SQLite database")
    parser.add_argument("--equity-evidence", help="human reviewed equity issuance JSON")
    parser.add_argument("--expected-fiscal-end", help="optional hard guard against stale annual period")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-html", required=True)
    args = parser.parse_args(argv)
    if args.download and not args.snapshot_out:
        parser.error("--download requires --snapshot-out to preserve raw evidence")
    if args.snapshot_out and not args.download:
        parser.error("--snapshot-out requires --download")
    cik = _validate_cik(args.cik)
    paths = [Path(args.out_json).resolve(), Path(args.out_html).resolve()]
    if args.companyfacts:
        paths.append(Path(args.companyfacts).resolve())
    if args.snapshot_out:
        paths.append(Path(args.snapshot_out).resolve())
    if args.equity_evidence:
        paths.append(Path(args.equity_evidence).resolve())
    if args.ratings_db:
        paths.append(Path(args.ratings_db).resolve())
    if len(set(paths)) != len(paths):
        parser.error("input/output paths must be different")

    if args.download:
        raw = download_companyfacts(cik, user_agent=os.getenv("SEC_USER_AGENT", ""))
        mode = "sec_direct_download"
    else:
        raw = json.loads(Path(args.companyfacts).read_text(encoding="utf-8"))
        mode = "offline_file"
    evidence = (json.loads(Path(args.equity_evidence).read_text(encoding="utf-8"))
                if args.equity_evidence else None)
    report = build_company_research(
        raw, as_of=args.as_of, expected_cik=cik, sector=args.sector,
        expected_fiscal_end=args.expected_fiscal_end, credit_db=args.ratings_db,
        equity_offering_evidence=evidence, input_mode=mode)
    page = render_company_research(report)
    if args.snapshot_out:
        snapshot = Path(args.snapshot_out)
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(json.dumps(raw, ensure_ascii=False, indent=2,
                                       allow_nan=False), encoding="utf-8")
        report["source"]["snapshot_saved_at"] = str(snapshot)
    dest_json, dest_html = Path(args.out_json), Path(args.out_html)
    for path in (dest_json, dest_html):
        path.parent.mkdir(parents=True, exist_ok=True)
    dest_json.write_text(json.dumps(report, indent=2, ensure_ascii=False,
                                    allow_nan=False), encoding="utf-8")
    dest_html.write_text(page, encoding="utf-8")
    print(f"CIK {report['cik']} | {report['coverage_status']} | "
          f"Piotroski {report['quality']['piotroski']['score_range']} | "
          f"TTM {report['ttm_crosscheck']['status']}")


if __name__ == "__main__":
    main()
