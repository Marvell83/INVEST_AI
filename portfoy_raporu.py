"""Safe, offline Turkish HTML presentation for INVEST_AI portfolio-risk JSON.

No external CSS, charts, scripts, trades, or unverified market data downloads.
"""
from __future__ import annotations

import argparse
from html import escape
import json
import math
from pathlib import Path

from portfoy_risk import VERSION


def _txt(value):
    return escape(str(value), quote=True)


def _num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("nonfinite or invalid numeric portfolio value")
    return float(value)


def _fmt(value, decimals=2):
    if value is None:
        return "Bilinmiyor"
    formatted = f"{_num(value):,.{decimals}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _row(cells):
    return "<tr>" + "".join("<td>" + _txt(v) + "</td>" for v in cells) + "</tr>"


def _section(title, headers, rows):
    head = "".join("<th>" + _txt(t) + "</th>" for t in headers)
    body = "".join(_row(row) for row in rows)
    if not body:
        body = '<tr><td colspan="' + str(len(headers)) + '">Veri bulunmuyor</td></tr>'
    return ('<section><h2>' + _txt(title) + '</h2><div class="scroll"><table><thead><tr>' +
            head + '</tr></thead><tbody>' + body + '</tbody></table></div></section>')


def render_portfolio_html(report):
    if (not isinstance(report, dict) or report.get("schema_version") != VERSION or
            report.get("status") != "ANALYSIS_FROM_USER_INPUTS"):
        raise ValueError("supported INVEST_AI portfolio audit JSON required")
    positions = report.get("positions")
    if not isinstance(positions, list) or not positions:
        raise ValueError("portfolio report must contain holdings")
    as_of = _txt(report.get("as_of"))
    total = _fmt(report["total_market_value_usd"])
    invested = _fmt(report["invested_market_value_usd"])
    cash = _fmt(report["cash_usd"])
    top3 = _fmt(report["top_three_pct_of_invested"], 1)
    positions_table = _section("Mevcut pozisyonlar", [
        "Hisse", "Adet", "Fiyat (USD)", "Fiyat tarihi", "Piyasa değeri (USD)",
        "Ağırlık (% toplam)", "USD kâr/zarar", "Sektör", "Temalar"], [
        [p["ticker"], p["quantity"], _fmt(p["price_usd"]),
         p["price_date"], _fmt(p["market_value_usd"]), _fmt(p["weight_total_pct"], 2),
         _fmt(p["unrealized_pnl_usd"]), p["sector"], ", ".join(p["themes"]) or "Etiketsiz"]
        for p in positions
    ])
    sectors = _section("Sektörel dağılım", ["Sektör", "USD", "Toplam portföy (%)"], [
        [x["label"], _fmt(x["market_value_usd"]), _fmt(x["weight_total_pct"], 2)]
        for x in report["sector_allocation"]
    ])
    themes = _section("Örtüşebilen yatırım temaları", ["Tema", "USD", "Toplam portföy (%)"], [
        [x["label"], _fmt(x["market_value_usd"]), _fmt(x["weight_total_pct"], 2)]
        for x in report["theme_exposures"]
    ])
    unions = _section("Tekrarsız tema birleşimleri", ["Grup", "Hisseler", "USD", "Toplam (%)"], [
        [x["label"], ", ".join(x["tickers"]), _fmt(x["market_value_usd"]),
         _fmt(x["weight_total_pct"], 2)] for x in report["theme_unions"]
    ])
    scenario_section = _section("Varsayımsal stres senaryoları", [
        "Senaryo", "Süre", "USD değişim", "Toplam getiri (%)", "Stres sonrası USD"], [
        [x["name"], x["horizon"], _fmt(x["impact_usd"]), _fmt(x["portfolio_return_pct"]),
         _fmt(x["post_stress_value_usd"])] for x in report["scenarios"]
    ])
    fx = ""
    if report.get("fx_usdtry"):
        record = report["fx_usdtry"]
        fx = ('<p class="fine">Güncel TL karşılığı: <strong>' +
              _fmt(record["total_market_value_try"]) + ' TL</strong> (' +
              _fmt(record["rate"], 4) + ' USD/TRY, ' + _txt(record["date"]) +
              '). Bu değer TL kâr/zarar değildir.</p>')
    warn = "".join("<li>" + _txt(w) + "</li>" for w in report.get("warnings", []))
    if not warn:
        warn = "<li>Veri uyarısı bildirilmedi; bu kaynak doğrulaması anlamına gelmez.</li>"
    limitations = "".join("<li>" + _txt(w) + "</li>" for w in report.get("limitations", []))
    overview = "".join(
        '<div class="metric"><small>' + title + '</small><strong>' + value + '</strong></div>'
        for title, value in (
            ("Toplam USD", total), ("Yatırımdaki USD", invested),
            ("Nakit USD", cash), ("En büyük üç pozisyon (%)", top3))
    )
    return (
        '<!doctype html><html lang="tr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>INVEST_AI — Portföy Risk Raporu</title>'
        '<style>'
        ':root{color-scheme:light;font-family:system-ui,Segoe UI,sans-serif;}'
        'body{background:#f5f7fb;color:#1f2937;margin:0;padding:22px;}'
        'main{max-width:1200px;margin:auto;}'
        'header{background:#182943;color:white;padding:24px;border-radius:14px;}'
        'h1{margin:0 0 8px;font-size:27px;}h2{font-size:18px;margin:0 0 14px;}'
        'header p{color:#cbd5e1;margin:0;}'
        '.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:16px 0;}'
        '.metric{background:white;border:1px solid #e0e6ef;border-radius:12px;padding:16px;}'
        '.metric small{display:block;color:#64748b;margin-bottom:9px;}'
        '.metric strong{font-size:23px;font-variant-numeric:tabular-nums;}'
        'section{background:white;border:1px solid #e0e6ef;border-radius:12px;'
        'padding:18px;margin:15px 0;}'
        '.scroll{overflow-x:auto;}table{border-collapse:collapse;width:100%;font-size:13px;}'
        'th,td{text-align:left;border-bottom:1px solid #e5eaf1;padding:11px;white-space:nowrap;}'
        'th{background:#f1f5f9;color:#334155;}tr:last-child td{border-bottom:0;}'
        '.fine{font-size:13px;color:#53657d;}li{margin:5px 0;}'
        '.notice{background:#fff5dc;border-left:4px solid #c4861d;padding:12px;margin:16px 0;}'
        '</style></head><body><main>'
        '<header><h1>INVEST_AI | Portföy Risk Analizi</h1>'
        '<p>Bilgi kesme tarihi: ' + as_of + ' · Kullanıcının verdiği fiyat ve varsayımlar</p></header>'
        '<div class="notice"><strong>Uyarı:</strong> Bu rapor canlı fiyat kaynağı değil; '
        'işlem önerisi veya getiri tahmini üretmez. Temalar kullanıcı tarafından sınıflandırılmıştır.</div>'
        '<div class="metrics">' + overview + '</div>' + fx +
        positions_table + sectors + themes +
        '<p class="fine">Tema yüzdeleri örtüşebilir. AI gibi birleşik temalarda '
        'aynı hisseyi bir kez saymak için aşağıdaki birleşimleri kullanın.</p>' +
        unions + scenario_section +
        '<section><h2>Veri uyarıları</h2><ul>' + warn + '</ul></section>'
        '<section><h2>Sınırlamalar</h2><ul>' + limitations + '</ul></section>'
        '</main></body></html>'
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render static offline Turkish portfolio-risk HTML")
    parser.add_argument("--report", required=True, help="result JSON from portfoy_risk.py")
    parser.add_argument("--out", required=True, help="output HTML path")
    args = parser.parse_args(argv)
    with open(args.report, encoding="utf-8") as reader:
        report = json.load(reader, parse_constant=lambda x: (_ for _ in ()).throw(ValueError("invalid JSON number")))
    result = render_portfolio_html(report)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(result, encoding="utf-8")
    print(f"Portfolio dashboard: {target}")


if __name__ == "__main__":
    main()
