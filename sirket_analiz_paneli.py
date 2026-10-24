"""INVEST_AI: offline, independent Piotroski / credit / experimental DCF dashboard.

Render previously created research JSON. No API calls, price feeds, blended
scores, investment recommendations or embedded third-party scripts.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import pathlib
import re

VERSION = "quality-panel-0.1.0"
SIGNALS = {
    "ROA_POSITIVE": "Pozitif aktif kârlılığı",
    "CFO_POSITIVE": "Pozitif faaliyet nakit akışı",
    "DELTA_ROA": "Aktif kârlılığı iyileşiyor",
    "QUALITY_OF_EARNINGS": "Faaliyet nakdi net kârdan yüksek",
    "DELTA_LEVERAGE": "Uzun vadeli borç oranı düşüyor",
    "DELTA_LIQUIDITY": "Cari oran iyileşiyor",
    "NO_EQUITY_OFFERING": "Yeni özsermaye ihracı yok",
    "DELTA_GROSS_MARGIN": "Brüt kâr marjı iyileşiyor",
    "DELTA_ASSET_TURNOVER": "Varlık devir hızı artıyor",
}

def _safe(value):
    return html.escape(str(value), quote=True)

def _money(value, unit="USD"):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return "Bilgi yok"
    scale, label = (1e12, "trilyon") if abs(value) >= 1e12 else (
        (1e9, "milyar") if abs(value) >= 1e9 else (
            (1e6, "milyon") if abs(value) >= 1e6 else (1, "")))
    return f"{value/scale:.2f} {label} {unit}".replace("  ", " ").strip()

def render_dashboard(quality, valuation=None):
    """Return self-contained, HTML-escaped, Turkish investor research layout."""
    if not isinstance(quality, dict) or not isinstance(quality.get("piotroski"), dict):
        raise ValueError("Piotroski quality snapshot required")
    p = quality["piotroski"]
    cik = quality.get("cik")
    if not isinstance(cik, str) or not re.fullmatch(r"\d{10}", cik) or p.get("cik") != cik:
        raise ValueError("quality CIK mismatch or invalid format")
    if not isinstance(p.get("signals"), dict):
        raise ValueError("Piotroski signals required")
    score_range = p.get("score_range")
    if not isinstance(score_range, list) or len(score_range) != 2:
        raise ValueError("Piotroski score range missing")

    rows = []
    for key, description in SIGNALS.items():
        v = p["signals"].get(key)
        if type(v) not in (int, type(None)) or v not in (0, 1, None):
            raise ValueError("invalid Piotroski signal")
        tag = "1" if v == 1 else ("0" if v == 0 else "?")
        css = "yes" if v == 1 else ("no" if v == 0 else "unknown")
        why = p.get("missing_reasons", {}).get(key, "")
        why = {
            "SECTOR_NOT_CONFIRMED": "Şirketin finans dışı sektörde olduğu doğrulanmadı; puanlama başlatılmadı.",
            "FINANCIAL_SECTOR_METHOD_UNAVAILABLE": "Finans kuruluşları için bu Piotroski yöntemi uygulanmıyor.",
        }.get(why, why)
        rows.append(f"<tr><td>{_safe(description)}</td><td class='{css}'>{tag}</td><td>{_safe(why)}</td></tr>")
    complete = p.get("known_count") == 9 and isinstance(p.get("score"), int)
    score = f"{p['score']} / 9" if complete else "Tamamlanmadı"
    detail = ("9 gösterge hesaplandı" if complete else
              f"Bilinen {p.get('known_count',0)}/9 · Olası aralık: {score_range[0]}–{score_range[1]}")

    credit = quality.get("credit")
    credit_rows = []
    if credit is not None:
        if not isinstance(credit, dict) or credit.get("cik") != cik:
            raise ValueError("credit CIK mismatch")
        for agency, item in sorted(credit.get("agency_ratings", {}).items()):
            url = item.get("source_url", "")
            source = (f'<a href="{_safe(url)}" rel="noopener noreferrer">Kaynak</a>'
                      if isinstance(url, str) and url.startswith("https://") else "Kaynak eksik")
            grade = item.get("investment_grade")
            status = "Yatırım yapılabilir" if grade is True else (
                "Spekülatif" if grade is False else "Not yok / geri çekildi")
            credit_rows.append(
                f"<tr><td>{_safe(agency)}</td><td>{_safe(item.get('rating',''))}</td>"
                f"<td>{_safe(item.get('outlook',''))}</td><td>{_safe(status)}</td>"
                f"<td>{_safe(item.get('published_date',''))}</td><td>{source}</td></tr>")
    if not credit_rows:
        credit_rows = ["<tr><td colspan='6'>Kaynaklı kredi notu kaydı verilmedi.</td></tr>"]

    warnings = []
    sector = p.get("sector", "unknown")
    sector_caution = {
        "unknown": "Şirket sektörü doğrulanmadığı için dokuz Piotroski koşulu da hesaplanmadı. Bu bir 0/9 puanı değildir. Finans dışı şirket sınıflandırması doğrulanırsa analizi yeniden çalıştırın.",
        "financial": "Finans kuruluşlarında bu genel Piotroski yöntemi kullanılmaz; sektöre özgü yöntem gerekir. Bu bir 0/9 puanı değildir.",
    }.get(sector)
    if sector_caution:
        warnings.append(sector_caution)
    if not complete:
        warnings.append("Eksik Piotroski verileri 0 puan sayılmaz; sonuç kesin bir skor değildir.")
    if credit:
        warnings.append("Kredi notları manuel kaynak kayıtlarıdır; kaynak doğruluğu otomatik teyit edilmez.")
    dcf_section = "<p class='muted'>Bu şirkete ait deneysel DCF kaydı bağlanmadı.</p>"
    if valuation is not None:
        if (not isinstance(valuation, dict) or valuation.get("cik") != cik
                or valuation.get("status") != "recorded_experimental"
                or not isinstance(valuation.get("valuation"), dict)
                or valuation["valuation"].get("durum") != "gecerli"):
            raise ValueError("experimental valuation CIK mismatch or invalid record")
        dcf = valuation["valuation"]
        pairs = (("Firma değeri", "firma_degeri", "USD"),
                 ("Özsermaye değeri", "ozsermaye_degeri", "USD"),
                 ("Model hisse başı değer", "hisse_basi_deger", "USD/hisse"))
        cards = "".join(f"<div class='metric'><small>{_safe(label)}</small>"
                        f"<strong>{_safe(_money(dcf.get(key), unit))}</strong></div>"
                        for label, key, unit in pairs)
        pct = dcf.get("uc_deger_payi")
        tv = f"{pct*100:.1f}%" if isinstance(pct, (int,float)) and math.isfinite(pct) else "Bilgi yok"
        cards += f"<div class='metric'><small>Uç dönem payı</small><strong>{_safe(tv)}</strong></div>"
        dcf_section = (f"<div class='metrics'>{cards}</div>"
                       f"<p>Motor: {_safe(dcf.get('motor_surumu','Bilinmiyor'))}</p>"
                       "<p class='muted'>Deneysel hesap; piyasa fiyatı veya tavsiye değildir.</p>")
        if quality.get("as_of") != valuation.get("historical_as_of"):
            warnings.append("Piotroski raporunun bilgi tarihi ile DCF tarihinin farklı olması sonuçları karşılaştırırken dikkate alınmalıdır.")

    name = quality.get("company") or p.get("company") or f"CIK {cik}"
    caution = "".join(f"<li>{_safe(x)}</li>" for x in warnings)
    style = """
      :root{--bg:#f5f7fb;--ink:#18314b;--line:#e0e6ef;--muted:#64748b;--accent:#23508e}
      *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
      font:15px/1.55 system-ui,Arial,sans-serif}
      main{max-width:1050px;margin:auto;padding:28px 20px 60px}
      .head{border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:20px}
      .brand{font-weight:800;letter-spacing:.13em;color:var(--accent)}h1{margin:8px 0;font-size:32px}
      h2{margin:0 0 14px;font-size:20px}p{margin:8px 0}.muted,small{color:var(--muted)}
      .grid,.metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
      .card{background:white;border:1px solid var(--line);border-radius:12px;padding:22px;margin-bottom:16px}
      strong.big{display:block;font-size:34px;margin:10px 0}
      table{border-collapse:collapse;width:100%;font-size:13px}
      th,td{border-bottom:1px solid var(--line);padding:10px 8px;text-align:left;vertical-align:top}
      th{background:#f2f6fc}.scroll{overflow:auto}.yes{color:#168250;font-weight:bold}
      .no{color:#b73b3b;font-weight:bold}.unknown{color:#ab851f;font-weight:bold}
      .metric{background:#f3f7fc;border-radius:8px;padding:13px}.metric strong{display:block;font-size:19px}
      .note{border-left:4px solid #bb8d24;padding:10px 16px;background:#fff9eb}
      a{color:#23508e}@media(max-width:640px){.grid,.metrics{grid-template-columns:1fr}}
    """
    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>INVEST_AI | {_safe(name)}</title><style>{style}</style></head>
<body><main><header class="head"><div class="brand">INVEST_AI · ARAŞTIRMA</div>
<h1>{_safe(name)}</h1><p class="muted">CIK {_safe(cik)} · Bilgi tarihi: {_safe(quality.get('as_of',''))}
· Tek bileşik puan yok</p></header>
<div class="grid"><section class="card"><h2>Piotroski F-Score</h2>
<strong class="big">{_safe(score)}</strong><p>{_safe(detail)}</p>
{("<div class='note'>" + _safe(sector_caution) + "</div>") if sector_caution else ""}</section>
<section class="card"><h2>Veri kapsamı</h2>
<p>Sektör: {_safe(p.get('sector','Bilinmiyor'))}</p>
<p>Son mali dönem: {_safe(p.get('periods',{}).get('current_fy_end','Bilinmiyor'))}</p>
<p>Metot: {_safe(p.get('version','Bilinmiyor'))}</p></section></div>
<section class="card"><h2>9 Piotroski koşulu</h2><div class="scroll">
<table><thead><tr><th>Ölçüt</th><th>1/0/?</th><th>Gerekçe</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></section>
<section class="card"><h2>Moody's / S&amp;P / Fitch — kredi kalitesi</h2>
<div class="scroll"><table><thead><tr><th>Kuruluş</th><th>Not</th><th>Görünüm</th>
<th>Sınıf</th><th>Tarih</th><th>Kaynak</th></tr></thead>
<tbody>{''.join(credit_rows)}</tbody></table></div></section>
<section class="card"><h2>DCF — deneysel değerleme</h2>{dcf_section}</section>
<section class="card"><h2>Yorum sınırları</h2><div class="note"><ul>{caution}</ul>
<p>Piotroski, kredi riski ve DCF ayrı kanıt katmanlarıdır.
Tek bir yatırım puanına dönüştürülmez.</p></div></section>
<p class="muted">INVEST_AI {VERSION} · Tamamen çevrimdışı HTML raporu · Yatırım tavsiyesi değildir.</p>
</main></body></html>"""

def main(argv=None):
    parser=argparse.ArgumentParser(description="Render INVEST_AI offline quality dashboard")
    parser.add_argument("--quality",required=True)
    parser.add_argument("--valuation")
    parser.add_argument("--out",required=True)
    args=parser.parse_args(argv)
    def load(path):
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    rendered=render_dashboard(load(args.quality),load(args.valuation) if args.valuation else None)
    out=pathlib.Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(rendered,encoding="utf-8")
    print("Written:",out)

if __name__=="__main__":
    main()
