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

from finansal_oranlar import RATIOS
from finansal_tablolar import DERIVED_ITEMS, LINE_ITEMS, STATEMENTS, line_item_label

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
    return f"{value / scale:.2f} {label} {unit}".replace("  ", " ").strip()

# Shared by every offline INVEST_AI HTML page (research report, variance report).
PAGE_STYLE = """
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
      td.num,th.num{text-align:right;white-space:nowrap}td.group{font-weight:bold;background:#f8fafd}
      a{color:#23508e}@media(max-width:640px){.grid,.metrics{grid-template-columns:1fr}}
    """
STATEMENT_TITLES = {"income": "Gelir tablosu", "cash_flow": "Nakit akışı", "balance": "Bilanço"}


def _statement_cell(cell):
    status = cell.get("status")
    if status in ("REPORTED", "DERIVED"):
        scale = 1e6
        text = f"{cell['value'] / scale:,.0f}" + ("†" if status == "DERIVED" else "")
        title = (f"{cell.get('method', '')} · {', '.join(cell.get('sources', []))}" if status == "DERIVED" else
                 f"{cell.get('concept', '')} · {cell.get('accession', '')} · {cell.get('filed', '')}")
        if cell.get("revised"):
            title += " · sonradan revize edildi"
        return f"<td class='num' title='{_safe(title)}'>{_safe(text)}</td>"
    if status == "CONFLICT":
        concepts = ", ".join(a["concept"] for a in cell.get("alternatives", []))
        return f"<td class='num no' title='{_safe(concepts)}'>çelişki</td>"
    return f"<td class='num muted' title='{_safe(cell.get('reason', ''))}'>—</td>"


def _ratio_text(key, value):
    kind = RATIOS[key][2]
    if kind == "percent":
        return f"{value * 100:.1f}%"
    if kind == "multiple":
        return f"{value:.2f}x"
    return f"{value / 1e6:,.0f}"


def render_financial_sections(statements, ratios):
    """Annual statements and ratios tables; values in millions as reported to SEC."""
    years = statements.get("years", [])
    if not years:
        return ("<section class='card'><h2>Finansal tablolar</h2>"
                "<p>Bilgi tarihine kadar uygun yıllık 10-K verisi bulunamadı; tablo üretilmedi.</p></section>")
    if ratios.get("cik") != statements.get("cik") or len(ratios.get("years", [])) != len(years):
        raise ValueError("ratios do not belong to these statements")
    head = "".join(f"<th class='num'>{_safe(y['fiscal_year_end'])}</th>" for y in years)
    rows = []
    for statement in STATEMENTS:
        rows.append(f"<tr><td class='group' colspan='{len(years) + 1}'>{_safe(STATEMENT_TITLES[statement])}</td></tr>")
        keys = [k for k, spec in LINE_ITEMS.items() if spec[0] == statement]
        keys += [k for k, spec in DERIVED_ITEMS.items() if spec[0] == statement]
        for key in keys:
            unit = " (milyon adet)" if LINE_ITEMS.get(key, ("", "", "USD"))[2] == "shares" else ""
            cells = "".join(_statement_cell(y[statement][key]) for y in years)
            rows.append(f"<tr><td>{_safe(line_item_label(key) + unit)}</td>{cells}</tr>")
    table = (
        "<section class='card'><h2>Finansal tablolar — yıllık 10-K (milyon USD)</h2>" +
        _conflict_note(statements) +
        "<div class='scroll'><table><thead><tr><th>Kalem</th>" + head + "</tr></thead><tbody>" +
        "".join(rows) + "</tbody></table></div>" + _shares_note(statements.get("shares_outstanding")) +
        "<p class='muted'>— bildirilmedi (sıfır sayılmaz) · † aynı SEC dosyasından türetildi · "
        "hücrenin üzerine gelince XBRL kavramı, accession ve dosyalama tarihi görünür. "
        "Serbest nakit akışı CFO − CapEx'tir, FCFF değildir.</p></section>")

    ratio_rows = []
    group = None
    for key, (label, ratio_group, _, formula) in RATIOS.items():
        if ratio_group != group:
            group = ratio_group
            ratio_rows.append(f"<tr><td class='group' colspan='{len(years) + 1}'>{_safe(group)}</td></tr>")
        cells = []
        for item in ratios["years"]:
            r = item["ratios"][key]
            if r["value"] is None:
                cells.append(f"<td class='num muted' title='{_safe(r.get('reason', ''))}'>—</td>")
            else:
                cells.append(f"<td class='num'>{_safe(_ratio_text(key, r['value']))}</td>")
        ratio_rows.append(f"<tr><td title='{_safe(formula)}'>{_safe(label)}</td>{''.join(cells)}</tr>")
    ratio_table = (
        "<section class='card'><h2>Finansal oranlar</h2>"
        "<div class='scroll'><table><thead><tr><th>Oran</th>" + head + "</tr></thead><tbody>" +
        "".join(ratio_rows) + "</tbody></table></div>"
        "<p class='muted'>Oran adının üzerine gelince formül, — işaretinin üzerine gelince hesaplanamama "
        "nedeni görünür. Net borç milyon USD'dir; menkul kıymetler ve kira yükümlülükleri dahil değildir. "
        "Geçmiş oranlar tahmin, puan veya yatırım tavsiyesi değildir.</p></section>")
    return table + ratio_table


QUARTER_ROWS = (("income", "revenue"), ("income", "gross_profit"), ("income", "operating_income"),
                ("income", "net_income"), ("cash_flow", "cfo"), ("cash_flow", "capex"),
                ("cash_flow", "free_cash_flow"), ("balance", "cash"), ("balance", "total_debt"),
                ("balance", "stockholders_equity"))


def _conflict_note(statements):
    conflicts = statements.get("conflicts", [])
    return (f"<div class='note'>{len(conflicts)} kalemde XBRL etiketleri birbirini tutmuyor; "
            "bu hücrelere değer yazılmadı ve manuel inceleme gerekir.</div>") if conflicts else ""


def _shares_note(shares):
    if not isinstance(shares, dict):
        return ""
    if shares.get("status") == "REPORTED":
        millions = f"{shares['value'] / 1e6:,.1f}"
        return (f"<p>Dolaşımdaki hisse (kapak sayfası, {_safe(shares['date'])}): "
                f"<strong>{_safe(millions)} milyon adet</strong> · "
                f"{_safe(shares['form'])} {_safe(shares['accession'])}</p>")
    reason = {"MULTIPLE_VALUES_POSSIBLY_SHARE_CLASSES":
              "birden fazla hisse sınıfı değeri var; toplanmadı, manuel inceleme gerekir",
              "NOT_REPORTED": "kapak sayfasında bildirilmedi"}.get(shares.get("reason"), shares.get("reason", ""))
    return f"<p class='muted'>Dolaşımdaki hisse: {_safe(reason)}.</p>"


LAYER_STATUS = {
    "MATCHED": "birebir eşleşti", "MATCHED_WITH_NOTES": "eşleşti, notlar var",
    "DIFFERENCES": "fark var — manuel inceleme gerekir", "NOT_APPLICABLE": "uygulanmadı",
    "NOT_COMPARABLE": "karşılaştırılamadı",
}
CHECK_STATUS = {
    "MATCH": "eşleşti", "VALUE_DIFFERS": "tutar farklı",
    "SHARED_CONFLICT": "ortak katmanda XBRL etiket çelişkisi", "SHARED_MISSING": "ortak katmanda değer yok",
    "SAME_VALUE_OTHER_FILING": "aynı tutar, farklı SEC dosyası",
    "YEAR_NOT_IN_SHARED_STATEMENTS": "bu yıl ortak tablolarda yok",
    "ROUNDING": "yuvarlama farkı (≤ %0,1)", "SHARED_INCOMPLETE": "ortak çeyreklerde eksik değer",
}
LAYER_REASONS = {
    "NO_PIOTROSKI_SEC_INPUTS": "Piotroski hiç SEC verisi kullanmadı (sektör veya iki yıllık dönem şartı)",
    "TTM_ENGINES_NOT_RECONCILED": "iki TTM motoru mutabık değil",
    "NO_FOUR_CONSECUTIVE_SHARED_QUARTERS_TO_TTM_END": "TTM bitişine kadar art arda dört ortak çeyrek yok",
}


def _millions(value):
    return "—" if value is None else f"{value / 1e6:,.0f}"


def render_layer_reconciliation(layers):
    """Where Piotroski / TTM inputs differ from the shared statements layer."""
    piotroski, ttm = layers.get("piotroski", {}), layers.get("ttm", {})
    rows = []
    for check in piotroski.get("checks", []):
        if check["status"] != "MATCH":
            rows.append(("Piotroski · " + check["piotroski_input"], check["fiscal_year_end"],
                         check["piotroski"], check.get("shared"), check["status"]))
    for check in ttm.get("checks", []):
        if check["status"] != "MATCH":
            rows.append(("TTM · " + check["metric"], ttm.get("ttm_end", ""),
                         check["ttm"], check.get("shared"), check["status"]))
    table = ""
    if rows:
        body = "".join(
            f"<tr><td>{_safe(name)}</td><td>{_safe(period)}</td><td class='num'>{_safe(_millions(old))}</td>"
            f"<td class='num'>{_safe(_millions(new))}</td><td>{_safe(CHECK_STATUS.get(status, status))}</td></tr>"
            for name, period, old, new, status in rows)
        table = ("<div class='scroll'><table><thead><tr><th>Kontrol</th><th>Dönem</th>"
                 "<th class='num'>Eski motor</th><th class='num'>Ortak katman</th><th>Durum</th></tr></thead>"
                 f"<tbody>{body}</tbody></table></div>")

    def line(title, part):
        checks = part.get("checks", [])
        matched = sum(c["status"] == "MATCH" for c in checks)
        reason = part.get("reason", "")
        detail = f" ({matched}/{len(checks)} kontrol birebir)" if checks else f" — {LAYER_REASONS.get(reason, reason)}"
        status = part.get("status", "NOT_APPLICABLE")
        css = "no" if status == "DIFFERENCES" else ("yes" if status == "MATCHED" else "")
        return (f"<p>{_safe(title)}: <span class='{css}'>{_safe(LAYER_STATUS.get(status, status))}</span>"
                f"{_safe(detail)}</p>")
    return (
        "<section class='card'><h2>Katman mutabakatı</h2>" +
        line("Piotroski girdileri ↔ yıllık tablolar", piotroski) +
        line("TTM ↔ son dört çeyreğin toplamı", ttm) + table +
        "<p class='muted'>Piotroski ve TTM motorları SEC verisini hâlâ kendi kurallarıyla okur. Bu bölüm, "
        "aynı SEC dosyasında onların kullandığı rakamları ortak tablo katmanıyla karşılaştırır (milyon USD). "
        "Eşleşme, SEC verisinin bağımsız doğrulandığı anlamına gelmez.</p></section>")


FORECAST_REASONS = {
    "LATEST_REVENUE_UNAVAILABLE_OR_NONPOSITIVE": "son yılın geliri yok veya pozitif değil",
    "LATEST_OPERATING_MARGIN_UNAVAILABLE": "son yılın faaliyet marjı hesaplanamadı",
    "FEWER_THAN_2_REVENUE_GROWTH_OBSERVATIONS": "en az iki yıllık gelir büyümesi gözlemi gerekir",
    "FEWER_THAN_2_OPERATING_MARGIN_OBSERVATIONS": "en az iki yıllık faaliyet marjı gözlemi gerekir",
}
FORECAST_WARNINGS = {
    "SHORT_HISTORY_ONLY_BASE_SCENARIO": "Geçmiş kısa (üçten az gözlem); yalnız baz senaryo gösterildi.",
    "HIGH_HISTORICAL_GROWTH_RARELY_PERSISTS": "Tarihsel medyan büyüme %25'in üzerinde; bu hız uzun süre nadiren korunur.",
    "LONG_RUN_GROWTH_ABOVE_TYPICAL_NOMINAL_ECONOMY": "Uzun vadeli büyüme %5'in üzerinde; tipik nominal ekonomik büyümeden yüksek.",
}
SCENARIO_LABELS = {"temkinli": "Temkinli", "baz": "Baz", "iyimser": "İyimser"}


def _pct(value):
    return "—" if value is None else f"{value * 100:.1f}%"


def render_forecast_section(baseline, projection=None):
    """Historical baseline statistics and, if the analyst gave a sourced long-run rate, scenarios."""
    def stat_row(label, stats, fmt=_pct):
        if not stats or stats.get("n", 0) == 0:
            return f"<tr><td>{_safe(label)}</td><td class='num' colspan='3'>—</td><td class='num'>0</td></tr>"
        return (f"<tr><td>{_safe(label)}</td><td class='num'>{_safe(fmt(stats['median']))}</td>"
                f"<td class='num'>{_safe(fmt(stats['q1']))}</td><td class='num'>{_safe(fmt(stats['q3']))}</td>"
                f"<td class='num'>{_safe(stats['n'])}</td></tr>")
    cagr = baseline.get("revenue_cagr")
    cagr_text = (f"Gelir yıllık bileşik büyümesi: {_pct(cagr['value'])} "
                 f"({cagr['from']} → {cagr['to']}, {cagr['years']} yıl)" if cagr else "")
    base = baseline.get("base", {})
    rows = "".join((
        stat_row("Yıllık gelir büyümesi", baseline.get("revenue_growth")),
        stat_row("Faaliyet kâr marjı", baseline.get("operating_margin")),
        stat_row("Efektif vergi oranı", baseline.get("effective_tax_rate")),
        stat_row("Serbest nakit akışı marjı", baseline.get("fcf_margin")),
        stat_row("Satış / yatırılan sermaye artışı", baseline.get("sales_to_capital"), lambda v: f"{v:.2f}x"),
    ))
    parts = [
        "<section class='card'><h2>Tarihsel baz ve senaryolar</h2>",
        f"<p>Son mali yıl: <strong>{_safe(baseline.get('base_fiscal_year_end') or 'Bilinmiyor')}</strong> · "
        f"gelir {_safe(_millions(base.get('revenue')))} milyon USD · faaliyet marjı "
        f"{_safe(_pct(base.get('operating_margin')))}</p>",
        f"<p>{_safe(cagr_text)}</p>" if cagr_text else "",
        "<div class='scroll'><table><thead><tr><th>Şirketin kendi geçmişi</th><th class='num'>Medyan</th>"
        "<th class='num'>Alt çeyrek</th><th class='num'>Üst çeyrek</th><th class='num'>Gözlem</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>",
    ]
    if baseline.get("status") != "OK":
        reasons = "; ".join(FORECAST_REASONS.get(r, r) for r in baseline.get("reasons", []))
        parts.append(f"<div class='note'>Senaryo üretmek için geçmiş yetersiz: {_safe(reasons)}.</div>")
    if projection is None:
        parts.append("<p class='muted'>Senaryo projeksiyonu için analistin kaynaklı uzun vadeli büyüme oranı "
                     "gerekir (ör. <code>--long-run-growth 0.03 --long-run-source \"…\"</code>). "
                     "Sistem bu oranı kendisi seçmez.</p>")
    elif projection.get("status") == "OK":
        assumptions = projection["assumptions"]
        scenario_rows = []
        for name, scenario in projection["scenarios"].items():
            for row in scenario["rows"]:
                scenario_rows.append(
                    f"<tr><td>{_safe(SCENARIO_LABELS.get(name, name))}</td><td>MY+{_safe(row['year'])}</td>"
                    f"<td class='num'>{_safe(_pct(row['revenue_growth']))}</td>"
                    f"<td class='num'>{_safe(_millions(row['revenue']))}</td>"
                    f"<td class='num'>{_safe(_pct(row['operating_margin']))}</td>"
                    f"<td class='num'>{_safe(_millions(row['operating_income']))}</td></tr>")
        warnings = "".join(f"<li>{_safe(FORECAST_WARNINGS.get(w, w))}</li>" for w in projection["warnings"])
        parts += [
            f"<p>Uzun vadeli büyüme (analist): <strong>{_safe(_pct(assumptions['long_run_growth']))}</strong> · "
            f"kaynak: {_safe(assumptions['long_run_growth_source'])}</p>",
            "<div class='scroll'><table><thead><tr><th>Senaryo</th><th>Yıl</th><th class='num'>Gelir büyümesi</th>"
            "<th class='num'>Gelir (milyon USD)</th><th class='num'>Faaliyet marjı</th>"
            "<th class='num'>Faaliyet kârı (milyon USD)</th></tr></thead>"
            f"<tbody>{''.join(scenario_rows)}</tbody></table></div>",
            f"<ul>{warnings}</ul>" if warnings else "",
        ]
        if projection.get("retrospective"):
            parts.append("<p class='muted'>Bilgi tarihi bugünden eski: bu senaryolar geçmişe dönük kurulmuştur, "
                         "o tarihte yapılmış bir tahmin gibi değerlendirilemez.</p>")
    else:
        reasons = "; ".join(FORECAST_REASONS.get(r, r) for r in projection.get("reasons", []))
        parts.append(f"<div class='note'>Senaryo üretilemedi: {_safe(reasons)}.</div>")
    parts.append(
        "<p class='muted'>Senaryolar şirketin kendi geçmişinin alt çeyrek / medyan / üst çeyrek büyüme ve marjından "
        "başlar; büyüme son yılda analistin uzun vadeli oranına, marj senaryo hedefine doğrusal olarak ulaşır. "
        "Bunlar olasılık tahmini, hedef fiyat veya yatırım tavsiyesi değildir.</p></section>")
    return "".join(parts)


VALUATION_INPUT_LABELS = {
    "discount_rate": "İskonto oranı", "terminal_growth": "Uç dönem büyümesi", "tax_rate": "Vergi oranı",
    "sales_to_capital": "Satış / yatırılan sermaye", "net_debt": "Net borç (milyon USD)",
    "shares": "Hisse sayısı (milyon adet)", "terminal_roic": "Uç dönem yeni yatırım getirisi (RONIC)",
}
VALUATION_ORIGINS = {"ANALYST": "Analist", "SEC_HISTORY": "Şirket geçmişi (SEC)", "SEC_FILING": "SEC dosyası",
                     "METHOD_DEFAULT": "Yöntem varsayılanı"}
VALUATION_WARNINGS = {
    "NET_DEBT_EXCLUDES_SECURITIES_AND_LEASES": "Net borç SEC tablolarından: menkul kıymetler ve kira yükümlülükleri "
                                               "dahil değil. Büyük menkul kıymet portföyü olan şirkette değer düşük çıkar.",
    "TERMINAL_RONIC_NEUTRAL_DEFAULT": "Uç dönem RONIC iskonto oranına eşit alındı: uzun vadeli büyüme değer yaratmaz, "
                                      "bu yüzden uç büyüme duyarlılığı küçüktür.",
    "RETROSPECTIVE_PROJECTION": "Bilgi tarihi bugünden eski; değerleme geçmişe dönük kurulmuştur.",
    "UC_DEGER_BASKIN": "Uç dönem değeri firma değerinin %85'inden fazlası.",
    "NEGATIF_FCFF_YILLARI": "Bazı yıllarda serbest nakit akışı negatif.",
    "OZSERMAYE_NEGATIF": "Özkaynak değeri negatif.",
    "UC_ROIC_YUKSEK_KANIT_GEREKLI": "Uç dönem RONIC iskontonun belirgin üzerinde; kalıcı rekabet avantajı kanıtı gerekir.",
    "UC_ROIC_ISKONTO_ALTINDA": "Uç dönem RONIC iskontonun altında: büyüme değer yok eder.",
    "NEGATIF_YATIRIM_SERMAYE_CIKISI_VARSAYIMI": "Gelir düşen yıllarda sermaye geri çekiliyor varsayılır.",
    "UC_VERGI_NORMALIZE_EDILDI": "Uç dönemde vergi normalleştirildi; devreden zarar sonsuza taşınmaz.",
}
MISSING_INPUT_HINTS = {
    "tax_rate": "vergi oranı geçmişten hesaplanamadı", "sales_to_capital": "satış / sermaye geçmişten hesaplanamadı",
    "net_debt": "net borç SEC tablolarından hesaplanamadı", "shares": "kapak sayfası hisse sayısı yok veya çok sınıflı",
}


def render_valuation_section(valuation):
    """Experimental scenario DCF: inputs with origin, scenario values, base sensitivity grid."""
    def input_value(name, value):
        if name in ("net_debt", "shares"):
            return f"{value / 1e6:,.1f}"
        if name == "sales_to_capital":
            return f"{value:.2f}x"
        return _pct(value)
    inputs = valuation.get("inputs", {})
    input_rows = "".join(
        f"<tr><td>{_safe(VALUATION_INPUT_LABELS.get(name, name))}</td>"
        f"<td class='num'>{_safe(input_value(name, item['value']))}</td>"
        f"<td>{_safe(VALUATION_ORIGINS.get(item['origin'], item['origin']))}</td><td>{_safe(item['source'])}</td></tr>"
        for name, item in inputs.items() if item.get("value") is not None)
    parts = ["<section class='card'><h2>Senaryo değerlemesi (deneysel DCF)</h2>"]
    if input_rows:
        parts.append("<div class='scroll'><table><thead><tr><th>Girdi</th><th class='num'>Değer</th><th>Köken</th>"
                     f"<th>Kaynak</th></tr></thead><tbody>{input_rows}</tbody></table></div>")
    status = valuation.get("status")
    if status == "INPUTS_MISSING":
        missing = "; ".join(MISSING_INPUT_HINTS.get(m, m) for m in valuation.get("missing", []))
        parts.append(f"<div class='note'>Değerleme için eksik girdi: {_safe(missing)}. Bu girdiler kaynağıyla "
                     "birlikte analist tarafından verilmelidir (<code>senaryo_degerleme.py</code>).</div>")
    elif status == "PROJECTION_UNAVAILABLE":
        parts.append("<div class='note'>Senaryo projeksiyonu üretilemediği için değerleme yapılmadı.</div>")
    elif status == "OK":
        rows = "".join(
            f"<tr><td>{_safe(SCENARIO_LABELS.get(name, name))}</td>"
            f"<td class='num'>{_safe(_millions(item['enterprise_value']))}</td>"
            f"<td class='num'>{_safe(_millions(item['equity_value']))}</td>"
            f"<td class='num'><strong>{_safe(_per_share(item['per_share']))}</strong></td>"
            f"<td class='num'>{_safe(_pct(item['terminal_value_share']))}</td></tr>"
            for name, item in valuation["scenarios"].items())
        parts.append("<p><strong>Senaryo değerleri</strong></p>"
                     "<div class='scroll'><table><thead><tr><th>Senaryo</th><th class='num'>Firma değeri (milyon USD)</th>"
                     "<th class='num'>Özkaynak değeri (milyon USD)</th><th class='num'>Hisse başı (USD)</th>"
                     f"<th class='num'>Uç değer payı</th></tr></thead><tbody>{rows}</tbody></table></div>")
        grid = valuation["sensitivity"]
        head = "".join(f"<th class='num'>g = {_safe(_pct(g))}</th>" for g in grid["terminal_growths"])
        body = []
        for i, (rate, line) in enumerate(zip(grid["discount_rates"], grid["per_share"])):
            cells = []
            for j, value in enumerate(line):
                text = _per_share(value) if value is not None else "—"
                cell = f"<strong>{_safe(text)}</strong>" if (i, j) == (2, 2) else _safe(text)
                cells.append(f"<td class='num'>{cell}</td>")
            body.append(f"<tr><td>iskonto {_safe(_pct(rate))}</td>{''.join(cells)}</tr>")
        parts.append(f"<p>Duyarlılık — {_safe(SCENARIO_LABELS.get(grid['scenario'], grid['scenario']))} senaryo, "
                     "hisse başı USD (iskonto × uç dönem büyümesi):</p>"
                     f"<div class='scroll'><table><thead><tr><th></th>{head}</tr></thead>"
                     f"<tbody>{''.join(body)}</tbody></table></div>")
        warnings = list(valuation.get("warnings", []))
        for item in valuation["scenarios"].values():
            warnings += [w for w in item["engine_warnings"] if w not in warnings]
        if warnings:
            parts.append("<ul>" + "".join(f"<li>{_safe(VALUATION_WARNINGS.get(w, w))}</li>" for w in warnings) + "</ul>")
    parts.append("<p class='muted'>Her senaryo, yukarıdaki projeksiyonla aynı gelir ve faaliyet marjı yolunu "
                 "deneysel v0.2 DCF motorunda değerler. — işareti geçersiz kombinasyondur (uç büyüme ≥ iskonto veya "
                 "%4 tavanın üstü). Hedef fiyat, adil değer veya yatırım tavsiyesi değildir.</p></section>")
    return "".join(parts)


def _per_share(value):
    return f"{value:,.2f}"


def render_quarterly_section(quarterly):
    """Discrete fiscal quarters (newest first); values in millions as reported to SEC."""
    quarters = quarterly.get("quarters", [])
    if not quarters:
        return ("<section class='card'><h2>Çeyreklik tablolar</h2>"
                "<p>Bilgi tarihine kadar çeyrek sınırları belirlenebilen 10-Q verisi bulunamadı.</p></section>")
    head = "".join(f"<th class='num'>{_safe(q['fiscal_year_label'])} Ç{_safe(q['fiscal_quarter'])}"
                   f"<br><small>{_safe(q['end'])}</small></th>" for q in quarters)
    rows = []
    for statement, key in QUARTER_ROWS:
        cells = "".join(_statement_cell(q[statement][key]) for q in quarters)
        rows.append(f"<tr><td>{_safe(line_item_label(key))}</td>{cells}</tr>")
    return (
        "<section class='card'><h2>Çeyreklik tablolar — 10-Q / 10-K (milyon USD)</h2>" +
        _conflict_note(quarterly) +
        "<div class='scroll'><table><thead><tr><th>Kalem</th>" + head + "</tr></thead><tbody>" +
        "".join(rows) + "</tbody></table></div>"
        "<p class='muted'>Çeyrekler mali yıla göredir (MY = mali yılın bittiği takvim yılı). "
        "† bildirilmiş 3 aylık değer yoksa mali yıl başından itibaren birikimli (YTD) iki değerin farkıdır; "
        "4. çeyrek yıllık 10-K eksi 9 aylık 10-Q'dur. Nakit akışı kalemleri SEC'e çoğunlukla yalnız "
        "YTD olarak bildirildiği için genellikle türetilmiştir.</p></section>")


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
            "TWO_COMPARABLE_ANNUAL_INCOME_PERIODS_REQUIRED": (
                "Karşılaştırılabilir iki yıllık 10-K net kâr dönemi bulunamadı; hesaplama yapılmadı."
            ),
        }.get(why, why)
        rows.append(f"<tr><td>{_safe(description)}</td><td class='{css}'>{tag}</td><td>{_safe(why)}</td></tr>")
    complete = p.get("known_count") == 9 and isinstance(p.get("score"), int)
    score = f"{p['score']} / 9" if complete else "Tamamlanmadı"
    detail = ("9 gösterge hesaplandı" if complete else
              f"Bilinen {p.get('known_count', 0)}/9 · Olası aralık: {score_range[0]}–{score_range[1]}")

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
                f"<tr><td>{_safe(agency)}</td><td>{_safe(item.get('rating', ''))}</td>"
                f"<td>{_safe(item.get('outlook', ''))}</td><td>{_safe(status)}</td>"
                f"<td>{_safe(item.get('published_date', ''))}</td><td>{source}</td></tr>")
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
    reasons = p.get("missing_reasons", {})
    annual_history_missing = (
        sector == "non_financial"
        and p.get("known_count") == 0
        and len(reasons) == len(SIGNALS)
        and set(reasons.values()) == {"TWO_COMPARABLE_ANNUAL_INCOME_PERIODS_REQUIRED"}
    )
    annual_caution = (
        "Piotroski hesaplanamadı: bu veri arşivinde iki karşılaştırılabilir yıllık "
        "10-K net kâr dönemi bulunmuyor. TTM için 10-K ve 10-Q verilerinin yeterli "
        "olması Piotroski için yeterli değildir. 0/9 hesaplanan gösterge sayısıdır, "
        "şirketin finansal kalite puanı değildir. Güncel tam SEC Company Facts "
        "verisiyle analizi yeniden çalıştırın."
        if annual_history_missing else None
    )
    if annual_caution:
        warnings.append(annual_caution)
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
        tv = f"{pct * 100:.1f}%" if isinstance(pct, (int, float)) and math.isfinite(pct) else "Bilgi yok"
        cards += f"<div class='metric'><small>Uç dönem payı</small><strong>{_safe(tv)}</strong></div>"
        dcf_section = (f"<div class='metrics'>{cards}</div>"
                       f"<p>Motor: {_safe(dcf.get('motor_surumu', 'Bilinmiyor'))}</p>"
                       "<p class='muted'>Deneysel hesap; piyasa fiyatı veya tavsiye değildir.</p>")
        if quality.get("as_of") != valuation.get("historical_as_of"):
            warnings.append("Piotroski raporunun bilgi tarihi ile DCF tarihinin farklı olması sonuçları karşılaştırırken dikkate alınmalıdır.")

    name = quality.get("company") or p.get("company") or f"CIK {cik}"
    caution = "".join(f"<li>{_safe(x)}</li>" for x in warnings)
    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>INVEST_AI | {_safe(name)}</title><style>{PAGE_STYLE}</style></head>
<body><main><header class="head"><div class="brand">INVEST_AI · ARAŞTIRMA</div>
<h1>{_safe(name)}</h1><p class="muted">CIK {_safe(cik)} · Bilgi tarihi: {_safe(quality.get('as_of', ''))}
· Tek bileşik puan yok</p></header>
<div class="grid"><section class="card"><h2>Piotroski F-Score</h2>
<strong class="big">{_safe(score)}</strong><p>{_safe(detail)}</p>
{("<div class='note'>" + _safe(sector_caution) + "</div>") if sector_caution else ""}
{("<div class='note'>" + _safe(annual_caution) + "</div>") if annual_caution else ""}</section>
<section class="card"><h2>Veri kapsamı</h2>
<p>Sektör: {_safe(p.get('sector', 'Bilinmiyor'))}</p>
<p>Son mali dönem: {_safe(p.get('periods', {}).get('current_fy_end', 'Bilinmiyor'))}</p>
<p>Metot: {_safe(p.get('version', 'Bilinmiyor'))}</p></section></div>
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
    parser = argparse.ArgumentParser(description="Render INVEST_AI offline quality dashboard")
    parser.add_argument("--quality", required=True)
    parser.add_argument("--valuation")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    def load(path):
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    rendered = render_dashboard(load(args.quality), load(args.valuation) if args.valuation else None)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rendered, encoding="utf-8")
    print("Written:", out)

if __name__ == "__main__":
    main()
