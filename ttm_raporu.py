"""Static HTML presentation of TTM statement arithmetic and optional DCF stress.

No JavaScript, external dependencies or network. Escapes all user-supplied text.
"""
from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path

LABELS = {
    "revenue": "Net satış / gelir", "ebit": "Faaliyet kârı (EBIT)",
    "gross_profit": "Brüt kâr", "net_income": "Net kâr",
    "cfo": "Faaliyet nakit akışı (CFO)", "capex": "Sermaye harcamaları (CapEx)",
}


def esc(value):
    return html.escape(str(value), quote=True)


def amount(value):
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return "—"
    return f"{value / 1e9:,.2f} milyar USD"


def render_ttm(ttm, dcf=None):
    if not isinstance(ttm, dict) or ttm.get("version") != "ttm-usgaap-0.1.0":
        raise ValueError("unsupported TTM data")
    if dcf is not None and (dcf.get("cik") != ttm.get("cik") or
                            dcf.get("historical_as_of") != ttm.get("as_of") or
                            dcf.get("ttm_fy_end") != ttm["periods"].get("current_9m_end")):
        raise ValueError("DCF and TTM do not reference same issuer or vintage")
    p = ttm["periods"]
    lines = []
    for key, label in LABELS.items():
        item = ttm["metrics"].get(key, {})
        if item.get("status") == "CALCULATED":
            values = [amount(item[phase]["value_usd"]) for phase in ("annual", "current_ytd9", "prior_ytd9")]
            source = item["current_ytd9"]
            metadata = f"{source['concept']} · {source['accession']} · {source['filed']}"
            result = amount(item["value_usd"])
        else:
            values = ["—"] * 3
            result = "Hesaplanamadı"
            metadata = item.get("status", "MISSING")
        lines.append("<tr><th>" + esc(label) + "</th>" +
                     "".join("<td>" + esc(x) + "</td>" for x in values) +
                     "<td class='value'>" + esc(result) + "</td></tr>" +
                     "<tr><td colspan='5' class='sub'>" + esc(metadata) + "</td></tr>")
    method = esc(ttm["method"])
    disclosure = ttm.get("input_disclosure") or {}
    kind = esc(disclosure.get("status", "USER_SUPPLIED_UNVERIFIED_SOURCE"))
    fyurl = disclosure.get("annual_source")
    qurl = disclosure.get("interim_source")
    links = []
    if isinstance(fyurl, str) and fyurl.startswith("https://www.sec.gov/Archives/"):
        links.append("<a href='" + esc(fyurl) + "' rel='noopener noreferrer'>SEC FY2025 10-K</a>")
    if isinstance(qurl, str) and qurl.startswith("https://www.sec.gov/Archives/"):
        links.append("<a href='" + esc(qurl) + "' rel='noopener noreferrer'>SEC FY2026 Q3 10-Q</a>")
    if not links:
        links.append("Kaynak bağlantıları belirtilmemiş")
    stats = [("TTM gelir", amount(ttm["metrics"]["revenue"].get("value_usd"))),
             ("TTM EBIT", amount(ttm["metrics"]["ebit"].get("value_usd"))),
             ("TTM faaliyet kâr marjı",
              f"{ttm['operating_margin'] * 100:.2f}%" if ttm.get("operating_margin") is not None else "—"),
             ("CFO - CapEx (FCFF değildir)", amount(ttm.get("cfo_less_capex_usd")))]
    cards = "".join("<div class='stat'><small>" + esc(title) + "</small><strong>" + esc(value) + "</strong></div>" for title,value in stats)
    dcf_sec = "<p class='muted'>Kaynaklı bir DCF senaryo analizi eklenmedi.</p>"
    if dcf:
        sections=[]
        for code,title in (("temkinli","Temkinli"),("baz","Baz"),("iyimser","İyimser")):
            row=dcf["scenarios"][code]
            val=row["valuation"]["hisse_basi_deger"]
            rate=row["assumptions"]["annual_revenue_growth"]
            sections.append(f"<div class='stat'><small>{title} · yıllık ciro büyümesi %{rate*100:g}</small>"+
                            f"<strong>{val:.2f} USD/hisse</strong>"+
                            "<small>Deneysel model; hedef fiyat değil</small></div>")
        reverse=dcf["reverse_dcf"]
        root=reverse.get("ima_edilen_buyume")
        reverse_text=f"%{root*100:.2f}" if root is not None else "Belirlenemedi"
        dcf_sec = (
            "<div class='grid'>" + "".join(sections) + "</div>"
            + "<p>Karşılaştırma fiyatı: <strong>" + esc(dcf["price_usd"]) + " USD</strong>"
            + " (tarih: " + esc(dcf["source_ages"]["quote_as_of"]) + "). "
            + "Baz senaryoda diğer girdiler sabitken ters DCF büyümesi: <strong>"
            + esc(reverse_text) + "</strong>. "
            + "Kök araması tüm çözümleri bulmayı garanti etmez.</p>"
        )
    warnings = list(ttm.get("warnings", [])) + list(dcf.get("warnings", []) if dcf else [])
    cautions="".join("<li>"+esc(w)+"</li>" for w in warnings)
    style="""
    :root{--bg:#f5f8fc;--paper:#fff;--ink:#172b43;--line:#dae4ef;--sub:#5a7088;--navy:#163f70}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.6 system-ui,Arial,sans-serif}
    main{max-width:1200px;margin:auto;padding:32px 20px 70px}
    .head{border-bottom:2px solid var(--navy);padding-bottom:18px;margin-bottom:18px}
    .eyebrow{letter-spacing:.12em;font-weight:800;color:var(--navy)}h1{margin:6px 0;font-size:30px}
    h2{margin-top:0;font-size:20px}.section{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:22px;margin:18px 0}
    .grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
    .stat{background:#f2f6fc;padding:16px;border-radius:8px;display:flex;flex-direction:column;gap:4px}
    .stat strong{font-size:22px}.muted,small{color:var(--sub)}.tablewrap{overflow:auto}
    table{border-collapse:collapse;width:100%;min-width:850px}th,td{padding:10px 12px;text-align:right;border-bottom:1px solid var(--line)}
    th:first-child{text-align:left}thead{background:#eef4fb}.sub{text-align:left;background:#fbfdff;font-size:11px;color:var(--sub)}
    .value{font-weight:750;color:var(--navy)}.note{border-left:3px solid #ab771d;background:#fff9ed;padding:10px 15px}
    a{color:var(--navy)}@media(max-width:670px){.grid{grid-template-columns:1fr}main{padding:18px 12px}}
    """
    return f"""<!doctype html><html lang='tr'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>INVEST_AI · {esc(ttm.get('company'))} TTM</title><style>{style}</style></head><body><main>
<div class='head'><div class='eyebrow'>INVEST_AI · TEMEL FİNANSAL ARAŞTIRMA</div>
<h1>{esc(ttm.get('company'))} — Son 12 ay (TTM)</h1><p class='muted'>CIK {esc(ttm.get('cik'))} · bilgi kesme tarihi {esc(ttm.get('as_of'))} · {esc(ttm.get('status'))}</p></div>
<section class='section'><h2>Finansal özet</h2><div class='grid'>{cards}</div>
<p class='muted'>Hesaplama: {method} · TTM dönemi bitişi {esc(p.get('current_9m_end'))}</p></section>
<section class='section'><h2>TTM bileşenleri ve izlenebilir kaynaklar</h2><div class='tablewrap'>
<table><thead><tr><th>Finansal kalem</th><th>FY bitiş {esc(p.get('annual_end'))}</th>
<th>Yeni 9 ay {esc(p.get('current_9m_end'))}</th><th>Önceki 9 ay {esc(p.get('prior_9m_end'))}</th><th>TTM</th></tr></thead>
<tbody>{''.join(lines)}</tbody></table></div><p class='muted'>Veri türü: {kind}</p>
<p>Birincil belgeler: {' · '.join(links)}</p></section>
<section class='section'><h2>Deneysel senaryolu DCF</h2>{dcf_sec}</section>
<section class='section'><h2>Veri ve model sınırları</h2><div class='note'><ul>{cautions}</ul></div></section>
<p class='muted'>Ücretsiz/açık kaynak mantığıyla üretilmiş statik HTML · yatırım tavsiyesi değildir</p></main></body></html>"""


def main(argv=None):
    parser=argparse.ArgumentParser(description="Offline TTM HTML report")
    parser.add_argument("--ttm",required=True)
    parser.add_argument("--dcf",help="optional dated DCF scenario JSON")
    parser.add_argument("--out",required=True)
    o=parser.parse_args(argv)
    ttm=json.loads(Path(o.ttm).read_text(encoding="utf-8"))
    dcf=json.loads(Path(o.dcf).read_text(encoding="utf-8")) if o.dcf else None
    output=Path(o.out); output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(render_ttm(ttm,dcf),encoding="utf-8")
    print("HTML:",output)

if __name__=="__main__":
    main()
