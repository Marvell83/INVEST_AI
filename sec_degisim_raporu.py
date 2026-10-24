"""INVEST_AI safe offline HTML for SEC snapshot changes and 9M-YoY observations.

Presentation only. Does not convert SEC archival differences into returns,
investment ratings or financial recommendations.
"""
from __future__ import annotations

import argparse
from html import escape
import json
import math
from pathlib import Path

from sec_finansal_degisim import VERSION
from sec_arsiv import atomic_write


def e(x):
    return escape(str(x), quote=True)


def f(x, digits=2):
    if x is None:
        return "Yok / hesaplanamadı"
    if isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x):
        raise ValueError("invalid value in financial change report")
    return f"{x:,.{digits}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def table(title, columns, items):
    head = "".join("<th>" + e(x) + "</th>" for x in columns)
    body = "".join(
        "<tr>" + "".join("<td>" + e(value) + "</td>" for value in row) + "</tr>"
        for row in items
    )
    return (
        '<section><h2>' + e(title) + '</h2><div class="scroll"><table><thead><tr>' +
        head + "</tr></thead><tbody>" + (body or
        '<tr><td colspan="' + str(len(columns)) + '">Kayıt yok</td></tr>') +
        "</tbody></table></div></section>"
    )


def render_change_report(report):
    if not isinstance(report, dict) or report.get("version") != VERSION:
        raise ValueError("INVEST_AI SEC change report version mismatch")
    if not isinstance(report.get("snapshot_record_changes"), dict):
        raise ValueError("missing SEC change event source")
    if not isinstance(report.get("new_snapshot_9m_yoy"), dict):
        raise ValueError("missing sourced 9M observations")
    change = report["snapshot_record_changes"]
    trend = report["new_snapshot_9m_yoy"]
    rows = []
    for metric, label in (
        ("revenue", "Gelir"), ("ebit", "Faaliyet kârı"),
        ("cfo", "Faaliyet nakit akışı"), ("capex", "Yatırım harcaması"),
    ):
        info = trend.get("items", {}).get(metric)
        if info:
            rows.append([
                label, f(info["prior_ytd9_usd"]), f(info["current_ytd9_usd"]),
                f(info["change_usd"]), (f(info["change_pct"]) + "%" if
                                       info["change_pct"] is not None else "Anlamsız / hesaplanamaz"),
                info["prior_source"]["accession"], info["current_source"]["accession"],
            ])
    trends = table("Karşılaştırılabilir 9 aylık dönemler (USD)", [
        "Metrik", "Önceki 9A", "Güncel 9A", "Fark", "Değişim", "Önceki kaynak", "Yeni kaynak"
    ], rows)
    margin = trend.get("margin")
    margin_html = ('<p>Faaliyet marjı: <strong>' +
                   f(margin["prior_operating_margin_pct"]) + '% → ' +
                   f(margin["current_operating_margin_pct"]) +
                   '%</strong> · Fark: ' + f(margin["change_percentage_points"]) +
                   ' yüzde puan</p>') if margin else (
                       "<p>Faaliyet marjı karşılaştırması kullanılamıyor.</p>")
    logs = []
    for record in change.get("events", []):
        item = record.get("current") or record.get("previous") or {}
        logs.append([
            record["kind"], item.get("metric", ""),
            item.get("concept", ""), item.get("kind", ""),
            item.get("start", ""), item.get("end", ""),
            item.get("form", ""), item.get("filed", ""),
            item.get("accession", ""), f(item.get("value_usd")),
        ])
    events = table("SEC arşiv kayıt değişiklikleri", [
        "Olay", "Metrik", "Kavram", "Dönem türü", "Başlangıç", "Bitiş",
        "Form", "Yayım", "Accession", "USD tutar"
    ], logs)
    old_hash = e(report.get("old_snapshot_sha256", ""))
    new_hash = e(report.get("new_snapshot_sha256", ""))
    reviews = "".join("<li>" + e(x) + "</li>"
                      for x in report.get("review_reasons", []))
    limitations = "".join("<li>" + e(x) + "</li>"
                          for x in report.get("limitations", []))
    return (
        '<!doctype html><html lang="tr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>INVEST_AI — SEC Finansal Değişimler</title>'
        '<style>'
        ':root{font-family:system-ui,Segoe UI,sans-serif;color:#21344d;background:#f4f6f9;}'
        'body{margin:0;padding:24px;}main{max-width:1200px;margin:auto;}'
        'header{border-radius:14px;background:#18314b;color:white;padding:24px;}'
        'h1{margin:0;font-size:28px}header p{color:#d2deeb;}'
        'section{background:white;border:1px solid #dce3ec;margin:16px 0;'
        'border-radius:12px;padding:18px;}h2{font-size:19px;margin:0 0 12px;}'
        'table{width:100%;border-collapse:collapse;font-size:13px;}'
        'th,td{text-align:left;border-bottom:1px solid #e2e8ef;padding:9px;}'
        'th{background:#f0f4fa;} .scroll{overflow-x:auto;}'
        '.notice{border-left:4px solid #b57b22;padding:14px;background:#fff8e9;}'
        '.secondary{font-size:13px;color:#576a81;word-break:break-word;}'
        'li{margin:8px 0;}'
        '</style></head><body><main><header><h1>INVEST_AI · SEC Finansal Değişimler</h1>'
        '<p>Şirket: ' + e(report.get("company") or "Bilinmiyor") +
        ' · CIK ' + e(report.get("cik", "")) +
        ' · Bilgi kesme tarihi: ' + e(report.get("as_of", "")) + '</p></header>'
        '<section class="notice"><strong>İki ayrı kavram:</strong> '
        'Aynı dönem için SEC kaynak kaydının değişmesi ekonomik büyüme değildir. '
        'Aşağıdaki dokuz aylık büyüme gözlemleri yalnızca tarihçe ve dönem '
        'uyumluluğu denetimi geçen veriyle hesaplanır; yatırım tahmini değildir.</section>'
        '<section><h2>Kaynak dosyaları ve denetim</h2>'
        '<p class="secondary">Eski SHA-256: ' + old_hash + '</p>'
        '<p class="secondary">Yeni SHA-256: ' + new_hash + '</p>'
        '<p>Dosya içerikleri aynı: <strong>' +
        ('Evet' if report.get("identical_snapshots") else 'Hayır') + '</strong></p>'
        '<p>SEC kayıt değişikliği sayısı: <strong>' + e(change.get("total", 0)) +
        '</strong>, gösterilen: <strong>' + e(len(change.get("events", []))) + '</strong></p>'
        '<p>Listeden çıkarılan olay sayısı: <strong>' + e(change.get("events_omitted", 0)) +
        '</strong></p>'
        '<p>Önceki TTM: ' + e(report.get("old_ttm_status", "")) +
        ' · Sonraki TTM: ' + e(report.get("new_ttm_status", "")) +
        ' · 9A durum: ' + e(trend.get("status", "")) + '</p></section>'
        + trends + '<section><h2>Dokuz aylık faaliyet marjı</h2>' + margin_html + '</section>' +
        events +
        '<section><h2>Manuel inceleme işaretleri</h2>' +
        ('<ul>' + reviews + '</ul>' if reviews else '<p>Yeni inceleme işareti yok.</p>') +
        '</section><section><h2>Yöntem sınırları</h2><ul>' + limitations +
        '</ul></section></main></body></html>'
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render safe offline SEC change HTML")
    parser.add_argument("--report", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if Path(args.report).resolve() == Path(args.out).resolve():
        parser.error("report and output must be separate paths")
    src = json.loads(Path(args.report).read_text(encoding="utf-8"))
    content = render_change_report(src)
    atomic_write(args.out, content.encode("utf-8"))
    print(f"Financial change HTML: {args.out}")


if __name__ == "__main__":
    main()
