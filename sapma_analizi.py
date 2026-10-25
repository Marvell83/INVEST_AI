"""INVEST_AI — forecast versus actual variance from the shared statements layer (roadmap lesson 8).

Forecasts in the append-only Tahmin Defteri are matched to the fiscal year they
target; the actual value is read from the shared annual statements (point in
time, with its SEC filing) and absolute, signed and percentage errors are
computed. Actuals are taken as FIRST REPORTED, so a later restatement does not
change how a forecast is judged. Nothing is written unless record=True; writes
are one transaction and idempotent.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
from pathlib import Path
import re
import statistics

from finansal_tablolar import MAX_YEARS, build_annual_statements, previous_year
from sirket_analiz_paneli import PAGE_STYLE
from tahmin_defteri import TahminDefteri

VERSION = "sapma-analizi-0.1.0"
# Ledger metric -> shared statements cell. "ebit" is the name used by sec_reviewed_pipeline.
METRICS = {"revenue": ("income", "revenue"), "operating_income": ("income", "operating_income"),
           "ebit": ("income", "operating_income")}
NOT_OBSERVABLE = {"fcff": "Issuers do not report FCFF; CFO minus CapEx is not FCFF"}
AFTER_PATTERN = re.compile(r"^FY\+(\d{1,2})_AFTER_(\d{4}-\d{2}-\d{2})$")  # tahmin_motoru
FY_END_PATTERN = re.compile(r"^FY_END:(\d{4}-\d{2}-\d{2})$")              # sec_reviewed_pipeline
FY_END_TOLERANCE_DAYS = 7  # 52/53-week fiscal calendars move the year end by a few days


def _date(value):
    return dt.date.fromisoformat(value)


def _resolve(target_period, statements):
    """The fiscal-year row a forecast targets, or (None, reason)."""
    years = statements["years"]
    match = AFTER_PATTERN.match(target_period)
    if match:
        steps, base = int(match.group(1)), match.group(2)
        index = next((i for i, y in enumerate(years) if y["fiscal_year_end"] == base), None)
        if index is None:
            return None, "BASE_YEAR_NOT_IN_STATEMENTS"
        target = index - steps
        if target < 0:
            return None, "NOT_YET_REPORTED"
        if any(previous_year(statements, i) is None for i in range(target, index)):
            return None, "FISCAL_YEAR_CHAIN_BROKEN"
        return years[target], None
    match = FY_END_PATTERN.match(target_period)
    if match:
        expected = _date(match.group(1))
        found = [y for y in years
                 if abs((_date(y["fiscal_year_end"]) - expected).days) <= FY_END_TOLERANCE_DAYS]
        if len(found) == 1:
            return found[0], None
        if found:
            return None, "AMBIGUOUS_TARGET_YEAR"
        latest = _date(years[0]["fiscal_year_end"]) if years else None
        if latest is None or expected > latest + dt.timedelta(days=FY_END_TOLERANCE_DAYS):
            return None, "NOT_YET_REPORTED"
        return None, "TARGET_YEAR_NOT_IN_STATEMENTS"
    return None, "UNSUPPORTED_TARGET_PERIOD"


def _actual(cell):
    """First-reported value of a reported cell, with the filing it came from."""
    first = cell.get("first_reported")
    if first:
        return first["value"], first["accession"], first["filed"]
    return cell["value"], cell["accession"], cell["filed"]


def _score(forecast, statements):
    row = {"forecast_id": forecast["id"], "metric": forecast["metric"],
           "target_period": forecast["target_period"], "predicted": forecast["predicted"],
           "scenario": forecast["assumptions"].get("scenario"), "model_version": forecast["model_version"],
           "forecast_as_of": forecast["assumptions"].get("as_of") or forecast["assumptions"].get("historic_as_of"),
           "created_at": forecast["created_at"]}
    if forecast["currency"] != "USD":
        return dict(row, status="UNSUPPORTED_CURRENCY")
    if forecast["metric"] in NOT_OBSERVABLE:
        return dict(row, status="NOT_OBSERVABLE", reason=NOT_OBSERVABLE[forecast["metric"]])
    if forecast["metric"] not in METRICS:
        return dict(row, status="UNSUPPORTED_METRIC")
    year, problem = _resolve(forecast["target_period"], statements)
    if problem:
        return dict(row, status=problem)
    statement, item = METRICS[forecast["metric"]]
    cell = year[statement][item]
    if cell["status"] != "REPORTED":
        return dict(row, status="ACTUAL_UNAVAILABLE", fiscal_year_end=year["fiscal_year_end"],
                    actual_status=cell["status"])
    actual, accession, filed = _actual(cell)
    signed = forecast["predicted"] - actual
    source = (f"SEC filing {accession} (filed {filed}); us-gaap:{cell['concept']}; "
              f"fiscal year {year['fiscal_year_start']}..{year['fiscal_year_end']}; first reported value")
    return dict(row, status="SCORED", fiscal_year_end=year["fiscal_year_end"], actual=actual,
                actual_accession=accession, actual_filed=filed, latest_actual=cell["value"],
                restated=bool(cell.get("revised")), outcome_source=source,
                absolute_error=abs(signed), signed_error=signed,
                percentage_error=signed / abs(actual) if actual else None)


def _summary(rows):
    scored = [r for r in rows if r["status"] == "SCORED"]
    groups = {}
    for r in scored:
        if r["percentage_error"] is not None:
            groups.setdefault((r["metric"], r["scenario"] or "-"), []).append(r["percentage_error"])
    accuracy = [{"metric": metric, "scenario": scenario, "n": len(errors),
                 "mean_absolute_percentage_error": statistics.fmean(abs(e) for e in errors),
                 "mean_signed_percentage_error": statistics.fmean(errors)}
                for (metric, scenario), errors in sorted(groups.items())]
    # Did the actual fall between the cautious and optimistic forecasts of the same projection?
    ranges = {}
    for r in scored:
        key = (r["metric"], r["target_period"], r["forecast_as_of"], r["model_version"])
        ranges.setdefault(key, {})[r["scenario"]] = r
    inside = [min(g["temkinli"]["predicted"], g["iyimser"]["predicted"]) <= g["temkinli"]["actual"]
              <= max(g["temkinli"]["predicted"], g["iyimser"]["predicted"])
              for g in ranges.values() if "temkinli" in g and "iyimser" in g]
    statuses = {}
    for r in rows:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    return {"forecasts": len(rows), "scored": len(scored), "by_status": statuses, "accuracy": accuracy,
            "scenario_range": {"ranges": len(inside), "actual_inside": sum(inside)}}


def analyze_variance(*, db_path, raw, as_of, record=False):
    """Match one issuer's ledger forecasts to SEC actuals; optionally record outcomes and scores."""
    statements = build_annual_statements(raw, as_of=as_of, years=MAX_YEARS)
    company = "CIK:" + statements["cik"]
    with TahminDefteri(db_path) as ledger:
        forecasts = [f for f in ledger.tahminleri_listele(ayrintili=True) if f["company"] == company]
        outcomes = {(o["company"], o["metric"], o["target_period"], o["currency"], o["source"]): o["id"]
                    for o in ledger.gerceklesenleri_listele()}
        evaluations = {(e["forecast_id"], e["outcome_id"]) for e in ledger.puanlari_listele()}
        rows = [_score(f, statements) for f in forecasts]
        for row in rows:
            if row["status"] == "SCORED":
                key = (company, row["metric"], row["target_period"], "USD", row["outcome_source"])
                row["already_recorded"] = (row["forecast_id"], outcomes.get(key)) in evaluations
        if record:
            ledger.db.execute("BEGIN IMMEDIATE")
            try:
                for row in rows:
                    if row["status"] != "SCORED" or row["already_recorded"]:
                        continue
                    key = (company, row["metric"], row["target_period"], "USD", row["outcome_source"])
                    if key not in outcomes:
                        outcomes[key] = ledger.gerceklesen_kaydet(
                            company=company, metric=row["metric"], target_period=row["target_period"],
                            currency="USD", actual=row["actual"], source=row["outcome_source"])
                    row["evaluation_id"] = ledger.puanla(row["forecast_id"], outcomes[key])["id"]
                    row["outcome_id"] = outcomes[key]
                ledger.db.commit()
            except Exception:
                ledger.db.rollback()
                raise
    return {"version": VERSION, "cik": statements["cik"], "company": statements.get("company", ""),
            "as_of": as_of, "recorded": record, "rows": rows, "summary": _summary(rows),
            "notes": ["Actuals are first-reported SEC values; restatements are shown but do not change scores",
                      "Signed error = forecast - actual; a positive percentage error is an over-forecast",
                      "FCFF forecasts are not scored: issuers do not report FCFF",
                      "Accuracy on a few forecasts is not evidence of future forecasting skill"]}


STATUS_LABELS = {
    "SCORED": "puanlandı", "NOT_YET_REPORTED": "henüz açıklanmadı", "NOT_OBSERVABLE": "gözlenemez (FCFF)",
    "ACTUAL_UNAVAILABLE": "gerçekleşen değer yok/çelişkili", "BASE_YEAR_NOT_IN_STATEMENTS": "taban yıl bulunamadı",
    "FISCAL_YEAR_CHAIN_BROKEN": "mali yıl zinciri kesik", "AMBIGUOUS_TARGET_YEAR": "hedef yıl belirsiz",
    "TARGET_YEAR_NOT_IN_STATEMENTS": "hedef yıl tablolarda yok", "UNSUPPORTED_TARGET_PERIOD": "dönem biçimi desteklenmiyor",
    "UNSUPPORTED_METRIC": "ölçüt desteklenmiyor", "UNSUPPORTED_CURRENCY": "para birimi desteklenmiyor",
}
METRIC_LABELS = {"revenue": "Gelir", "operating_income": "Faaliyet kârı", "ebit": "Faaliyet kârı (EBIT)",
                 "fcff": "FCFF"}
SCENARIO_LABELS = {"temkinli": "Temkinli", "baz": "Baz", "iyimser": "İyimser"}


def render_variance_html(report):
    """Self-contained Turkish page: every forecast, its actual and its error."""
    def safe(value):
        return html.escape(str(value), quote=True)

    def money(value):
        return "—" if value is None else f"{value / 1e6:,.0f}"

    def pct(value):
        return "—" if value is None else f"{value * 100:+.1f}%"

    def unsigned(value):
        return f"{value * 100:.1f}%"

    def metric(name):
        return METRIC_LABELS.get(name, name)

    def scenario(name):
        return SCENARIO_LABELS.get(name, name or "—")
    rows = "".join(
        f"<tr><td>{safe(r['forecast_id'])}</td><td>{safe(metric(r['metric']))}</td>"
        f"<td>{safe(scenario(r['scenario']))}</td>"
        f"<td>{safe(r['target_period'])}</td><td>{safe(r.get('fiscal_year_end', '—'))}</td>"
        f"<td class='num'>{safe(money(r['predicted']))}</td><td class='num'>{safe(money(r.get('actual')))}</td>"
        f"<td class='num'>{safe(pct(r.get('percentage_error')))}</td>"
        f"<td>{safe(STATUS_LABELS.get(r['status'], r['status']))}"
        f"{' · revize edildi' if r.get('restated') else ''}</td></tr>"
        for r in report["rows"])
    accuracy = "".join(
        f"<tr><td>{safe(metric(a['metric']))}</td><td>{safe(scenario(a['scenario']))}</td>"
        f"<td class='num'>{safe(a['n'])}</td>"
        f"<td class='num'>{safe(unsigned(a['mean_absolute_percentage_error']))}</td>"
        f"<td class='num'>{safe(pct(a['mean_signed_percentage_error']))}</td></tr>"
        for a in report["summary"]["accuracy"])
    span = report["summary"]["scenario_range"]
    span_text = (f"Gerçekleşen değer {span['actual_inside']}/{span['ranges']} durumda temkinli–iyimser "
                 "aralığının içinde kaldı." if span["ranges"] else "Temkinli–iyimser aralığı olan puanlanmış tahmin yok.")
    title = report.get("company") or "CIK " + report["cik"]
    accuracy = accuracy or "<tr><td colspan='5'>Henüz puanlanmış tahmin yok.</td></tr>"
    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>INVEST_AI | Sapma analizi | {safe(title)}</title><style>{PAGE_STYLE}</style></head>
<body><main><header class="head"><div class="brand">INVEST_AI · SAPMA ANALİZİ</div>
<h1>{safe(title)}</h1><p class="muted">CIK {safe(report['cik'])} · Bilgi tarihi: {safe(report['as_of'])}
· {safe(report['summary']['scored'])}/{safe(report['summary']['forecasts'])} tahmin puanlandı</p></header>
<section class="card"><h2>İsabet özeti</h2><p>{safe(span_text)}</p>
<div class="scroll"><table><thead><tr><th>Ölçüt</th><th>Senaryo</th><th class="num">Tahmin</th>
<th class="num">Ortalama mutlak % hata</th><th class="num">Ortalama yön (sapma)</th></tr></thead>
<tbody>{accuracy}</tbody></table></div>
<p class="muted">Pozitif sapma tahminin gerçekleşenden yüksek olduğunu gösterir. Az sayıda tahmine dayanan
isabet, gelecekteki tahmin başarısının kanıtı değildir.</p></section>
<section class="card"><h2>Tahmin ve gerçekleşen (milyon USD)</h2><div class="scroll"><table><thead><tr>
<th>No</th><th>Ölçüt</th><th>Senaryo</th><th>Hedef</th><th>Mali yıl</th><th class="num">Tahmin</th>
<th class="num">Gerçekleşen</th><th class="num">% hata</th><th>Durum</th></tr></thead><tbody>{rows}</tbody>
</table></div><p class="muted">Gerçekleşen değer SEC'e ilk bildirilen değerdir; sonradan revize edilse de
puan değişmez. FCFF şirketlerce bildirilmediği için puanlanmaz.</p></section>
<p class="muted">INVEST_AI {safe(VERSION)} · Çevrimdışı rapor · Yatırım tavsiyesi değildir.</p>
</main></body></html>"""


def main(argv=None):
    parser = argparse.ArgumentParser(description="Score ledger forecasts against SEC actuals (offline)")
    parser.add_argument("--ledger", required=True, help="Tahmin Defteri SQLite path")
    parser.add_argument("--companyfacts", required=True, help="raw SEC Company Facts JSON with newer filings")
    parser.add_argument("--as-of", required=True, help="knowledge cutoff YYYY-MM-DD")
    parser.add_argument("--record", action="store_true", help="write outcomes and scores to the ledger")
    parser.add_argument("--out", required=True)
    parser.add_argument("--out-html")
    args = parser.parse_args(argv)
    if not Path(args.ledger).is_file():
        parser.error("ledger file does not exist")
    raw = json.loads(Path(args.companyfacts).read_text(encoding="utf-8"))
    report = analyze_variance(db_path=args.ledger, raw=raw, as_of=args.as_of, record=args.record)
    for path, content in ((args.out, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)),
                          (args.out_html, render_variance_html(report) if args.out_html else None)):
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(content, encoding="utf-8")
    s = report["summary"]
    print(f"CIK {report['cik']} | {s['scored']}/{s['forecasts']} scored | recorded={report['recorded']} | {args.out}")


if __name__ == "__main__":
    main()
