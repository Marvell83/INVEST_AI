"""INVEST_AI — what SEC data alone can screen: quality filter over every processed issuer.

No prices and no PEG: only the issuer's own SEC statements. Each condition is
PASS / FAIL / PENDING (value missing); missing data is never a failure. The
universe is narrowed step by step and every step is counted, so the report
shows where companies drop out and why.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import csv
import html
import io
import json
import math
from pathlib import Path
import sqlite3

from hisse_tarama_tablosu import STALE_FINANCIALS_DAYS, financials_age_days
from sec_piyasa_toplu_tarama import DB_REL
from sec_sirket_profili import load_profiles

VERSION = "invest-ai-sec-quality-screen-0.1.0"
DEFAULT_MIN_REVENUE = 50_000_000
# (key, Turkish label, test); the reference rate enters ROE and ROIC.
CONDITIONS = (
    ("roe", "ROE > referans faiz", lambda v, rate: v > rate),
    ("roic", "ROIC > referans faiz", lambda v, rate: v > rate),
    ("net_debt_to_ebitda", "Net borç / FAVÖK* ≤ 2", lambda v, rate: v <= 2),
    ("cash_conversion_3y", "3 yıllık CFO / net kâr ≥ 1", lambda v, rate: v >= 1),
    ("fcf_3y", "3 yıllık toplam FCF > 0", lambda v, rate: v > 0),
)
TABLE = (("ticker", "Hisse", "text"), ("company", "Şirket", "text"), ("sector", "Sektör (SEC SIC)", "text"),
         ("fiscal_year", "Mali yıl sonu", "text"), ("revenue", "Gelir", "usd"),
         ("revenue_cagr_3y", "Gelir CAGR 3Y", "percent"), ("operating_margin", "Faaliyet marjı", "percent"),
         ("roe", "ROE", "percent"), ("roic", "ROIC", "percent"),
         ("net_debt_to_ebitda", "Net borç / FAVÖK*", "multiple"),
         ("cash_conversion_3y", "CFO / net kâr 3Y", "multiple"), ("fcf_3y", "FCF 3Y", "usd"),
         ("fcf_margin", "FCF marjı", "percent"), ("eps_cagr_3y", "EPS CAGR 3Y", "percent"),
         ("shares_change_3y", "Hisse adedi 3Y", "percent"))


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def judge(row, rate):
    """{condition: PASS / FAIL / PENDING} and the overall result."""
    checks = {}
    for key, _, test in CONDITIONS:
        value = _number(row.get(key))
        checks[key] = "PENDING" if value is None or (key in ("roe", "roic") and rate is None) else (
            "PASS" if test(value, rate) else "FAIL")
    overall = ("FAIL" if "FAIL" in checks.values() else "PENDING" if "PENDING" in checks.values() else "PASS")
    return checks, overall


def load_ok_rows(root):
    db = Path(root).resolve() / DB_REL
    if not db.is_file():
        raise FileNotFoundError("No local SEC screener database: run sec_piyasa_toplu_tarama.py first")
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as conn:
        meta = dict(conn.execute("SELECT key,value FROM metadata").fetchall())
        rows = [json.loads(p) for (p,) in conn.execute(
            "SELECT payload FROM companies WHERE status='OK' AND payload IS NOT NULL ORDER BY ticker")]
    return rows, meta.get("as_of")


def screen(rows, profiles, *, rate, min_revenue=DEFAULT_MIN_REVENUE, max_age=STALE_FINANCIALS_DAYS):
    """Narrow the universe step by step, then judge the five SEC-only conditions."""
    funnel = [{"step": "SEC finansalları işlenmiş şirketler (OK)", "count": len(rows)}]
    current = [r for r in rows if (age := financials_age_days(r.get("as_of"), r.get("fiscal_year"))) is not None
               and age <= max_age]
    funnel.append({"step": f"Son mali yılı en çok {max_age} gün önce biten (güncel)", "count": len(current)})
    operating, unknown_sector = [], 0
    for row in current:
        profile = profiles.get(row.get("cik"))
        if profile is None:
            unknown_sector += 1
        elif profile["financial"]:
            continue
        operating.append(dict(row, sector=(profile or {}).get("sic_description") or "Sektör bilinmiyor",
                              division=(profile or {}).get("division") or "Bilinmiyor",
                              sic=(profile or {}).get("sic"), exchanges=(profile or {}).get("exchanges")))
    funnel.append({"step": "Finans / sigorta / gayrimenkul (SIC 6000–6799) hariç", "count": len(operating),
                   "note": f"{unknown_sector} şirketin SEC profili yok; dahil tutuldu" if unknown_sector else None})
    sized = [r for r in operating if (_number(r.get("revenue")) or 0) >= min_revenue]
    funnel.append({"step": f"Yıllık gelir en az {min_revenue / 1e6:,.0f} milyon $", "count": len(sized)})

    per_condition = {key: {"PASS": 0, "FAIL": 0, "PENDING": 0} for key, _, _ in CONDITIONS}
    results = {"PASS": [], "FAIL": [], "PENDING": []}
    for row in sized:
        checks, overall = judge(row, rate)
        for key, state in checks.items():
            per_condition[key][state] += 1
        results[overall].append(dict(row, checks=checks, overall=overall))
    funnel.append({"step": "5 SEC koşulunun hepsini geçen", "count": len(results["PASS"])})
    passed = sorted(results["PASS"], key=lambda r: -(_number(r.get("roic")) or 0))
    by_division, by_sector = {}, {}
    for row in passed:
        by_division[row["division"]] = by_division.get(row["division"], 0) + 1
        by_sector[row["sector"]] = by_sector.get(row["sector"], 0) + 1

    def top(key, n=25, reverse=True, where=lambda r: True):
        usable = [r for r in passed if _number(r.get(key)) is not None and where(r)]
        return sorted(usable, key=lambda r: r[key], reverse=reverse)[:n]
    quality_growth = [r for r in passed
                      if (_number(r.get("roic")) or 0) >= 0.15 and not r.get("roic_warning")
                      and (_number(r.get("revenue_cagr_3y")) or 0) >= 0.10
                      and (_number(r.get("shares_change_3y")) if _number(r.get("shares_change_3y")) is not None
                           else 1) <= 0.05]
    return {
        "version": VERSION, "rate": rate, "min_revenue": min_revenue, "max_age_days": max_age,
        "funnel": funnel,
        "conditions": [{"key": k, "label": label, **per_condition[k]} for k, label, _ in CONDITIONS],
        "overall": {state: len(items) for state, items in results.items()},
        "by_division": dict(sorted(by_division.items(), key=lambda kv: -kv[1])),
        "by_sector": dict(sorted(by_sector.items(), key=lambda kv: -kv[1])[:20]),
        "roic_cautions_among_passed": sum(bool(r.get("roic_warning")) for r in passed),
        "passed": passed,
        "highlights": {
            "Kalite + büyüme: ROIC ≥ %15, 3Y gelir CAGR ≥ %10, hisse adedi 3Y artışı ≤ %5": quality_growth,
            "En yüksek ROIC (uyarısız)": top("roic", where=lambda r: not r.get("roic_warning")),
            "En hızlı büyüyen gelir (3Y CAGR)": top("revenue_cagr_3y"),
            "En yüksek FCF marjı": top("fcf_margin"),
        },
    }


def _fmt(value, kind):
    value_ = _number(value)
    if kind == "text":
        return "" if value is None else str(value)
    if value_ is None:
        return "—"
    if kind == "percent":
        return f"%{value_ * 100:.1f}".replace(".", ",")
    if kind == "multiple":
        return f"{value_:.2f}x".replace(".", ",")
    for scale, unit in ((1e9, " mr $"), (1e6, " mn $")):
        if abs(value_) >= scale:
            return f"{value_ / scale:,.1f}{unit}".replace(",", " ").replace(".", ",")
    return f"{value_:,.0f} $"


def passed_csv(result):
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([label for _, label, _ in TABLE] + ["ROIC uyarısı"])
    for row in result["passed"]:
        cells = []
        for key, _, kind in TABLE:
            value = row.get(key)
            if kind == "text":
                text = "" if value is None else str(value)
                cells.append("'" + text if text[:1] in ("=", "+", "-", "@") else text)
            else:
                number = _number(value)
                cells.append("" if number is None else str(number * 100 if kind == "percent" else number).replace(".", ","))
        writer.writerow(cells + ["evet" if row.get("roic_warning") else ""])
    return "﻿" + buffer.getvalue()


def render_html(result, *, as_of):
    esc = html.escape

    def table(rows, limit=None):
        head = "".join(f"<th>{esc(label)}</th>" for _, label, _ in TABLE)
        body = []
        for row in rows[:limit] if limit else rows:
            cells = []
            for key, _, kind in TABLE:
                text = _fmt(row.get(key), kind) + (" !" if key == "roic" and row.get("roic_warning") else "")
                cells.append(f"<td class='{'' if kind == 'text' else 'num'}'>{esc(text)}</td>")
            body.append("<tr>" + "".join(cells) + "</tr>")
        return f"<div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
    def count(n):
        return f"{n:,}".replace(",", ".")
    funnel = "".join(f"<tr><td>{esc(s['step'])}{('<br><small>' + esc(s['note']) + '</small>') if s.get('note') else ''}"
                     f"</td><td class='num'>{count(s['count'])}</td></tr>" for s in result["funnel"])
    conditions = "".join(f"<tr><td>{esc(c['label'])}</td><td class='num'>{c['PASS']}</td><td class='num'>{c['FAIL']}</td>"
                         f"<td class='num'>{c['PENDING']}</td></tr>" for c in result["conditions"])
    sectors = "".join(f"<tr><td>{esc(name)}</td><td class='num'>{n}</td></tr>" for name, n in result["by_division"].items())
    highlights = "".join(f"<h3>{esc(title)} ({len(rows)})</h3>" + table(rows, 25)
                         for title, rows in result["highlights"].items())
    rate = "verilmedi (ROE ve ROIC koşulları bekliyor)" if result["rate"] is None else f"%{result['rate'] * 100:.2f}"
    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>INVEST_AI SEC eleme</title>
<style>body{{font:14px/1.5 system-ui,Arial,sans-serif;margin:0;background:#f5f7fb;color:#18314b}}
main{{max-width:1200px;margin:auto;padding:24px 16px}}.card{{background:#fff;border:1px solid #e0e6ef;border-radius:12px;
padding:18px;margin-bottom:16px}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border-bottom:1px solid #e0e6ef;
padding:6px;text-align:left}}th{{background:#f2f6fc}}td.num{{text-align:right;white-space:nowrap}}.scroll{{overflow:auto}}
small{{color:#64748b}}</style></head><body><main>
<h1>Yalnız SEC verisiyle eleme</h1>
<p>SEC bilgi tarihi {esc(str(as_of))} · referans faiz {esc(rate)} · fiyat ve PEG kullanılmadı. Eksik veri elenme sebebi
sayılmaz, "veri bekliyor" olarak ayrılır. ROIC yanında ! işareti: yatırılan sermaye çok küçük (oran %100'ün üstünde).</p>
<section class="card"><h2>Huni</h2><table><tbody>{funnel}</tbody></table></section>
<section class="card"><h2>Koşullar</h2><table><thead><tr><th>Koşul</th><th>Geçti</th><th>Elendi</th><th>Veri bekliyor</th></tr></thead>
<tbody>{conditions}</tbody></table><p>Sonuç: {result['overall']['PASS']} geçti · {result['overall']['FAIL']} elendi ·
{result['overall']['PENDING']} veri bekliyor.</p></section>
<section class="card"><h2>Geçenlerin sektörleri (SIC bölümü)</h2><table><tbody>{sectors}</tbody></table></section>
<section class="card"><h2>Öne çıkanlar</h2>{highlights}</section>
<section class="card"><h2>5 koşulu geçen bütün şirketler ({len(result['passed'])})</h2>{table(result['passed'])}</section>
<p><small>FAVÖK* = faaliyet kârı + nakit akışı tablosundaki amortisman. Geçmiş SEC verisidir; değerleme, tahmin veya yatırım
tavsiyesi değildir.</small></p></main></body></html>"""


def main(argv=None):
    parser = argparse.ArgumentParser(description="SEC-only quality screen over every processed issuer")
    parser.add_argument("--root", default=".")
    parser.add_argument("--rate", type=float, help="reference rate in percent, e.g. 4.3 (10-year Treasury you verified)")
    parser.add_argument("--min-revenue", type=float, default=DEFAULT_MIN_REVENUE / 1e6, help="million USD")
    parser.add_argument("--out", default="reports/sec_eleme", help="output path without extension")
    args = parser.parse_args(argv)
    rows, as_of = load_ok_rows(args.root)
    result = screen(rows, load_profiles(args.root), rate=None if args.rate is None else args.rate / 100,
                    min_revenue=args.min_revenue * 1e6)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".html").write_text(render_html(result, as_of=as_of), encoding="utf-8")
    out.with_suffix(".csv").write_text(passed_csv(result), encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(dict(result, as_of=as_of), ensure_ascii=False, allow_nan=False),
                                        encoding="utf-8")
    for step in result["funnel"]:
        print(f"{step['count']:>6}  {step['step']}")
    print(f"Sonuç: {result['overall']}  ·  {out.with_suffix('.html')}")
    return 0


if __name__ == "__main__":
    main()
