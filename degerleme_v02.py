"""INVEST_AI experimental deterministic DCF v0.2.

This module does not replace the frozen 0.1 engine. All figures use a common
currency and consistent units. SBC uses the expense treatment only.
"""
from __future__ import annotations
import math

VERSION = "uretim-0.2.0-alpha"


def _num(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name}: finite numeric value required")
    return float(value)


def _series(value, n, name):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        result = [_num(value, name)] * n
    else:
        try:
            result = [_num(x, name) for x in value]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name}: invalid sequence") from exc
        if len(result) != n:
            raise ValueError(f"{name}: expected {n} years")
    return result


def degerle_v02(inputs):
    """Compute annual operating cash flows, terminal value, and per-share equity.

    Required: yillar, gelir_0, buyume, marj_0, marj_hedef, yakinlasma,
    satis_sermaye, vergi_orani, iskonto, uc_buyume, uc_roic, hisse.

    Optional: net_borc, baslangic_zarar, uc_buyume_tavani (default 0.04),
    iskonto_zamani (yil_sonu or yil_ortasi; with yil_ortasi only the explicit
    years move to t-0.5, the terminal value is still discounted at year n),
    sbc_marjda_dahil (default True), sbc_ilave_gider_orani (default 0),
    kalici_rekabet_avantaji (default False), marj_yolu (explicit annual
    operating margins for the `yillar` years; replaces the convergence formula,
    so marj_hedef / yakinlasma are then only validated, not used).

    Annual ROIIC is based on the previous year's reinvestment and the current
    change in operating profit after cash taxes; this is a diagnostic, not a
    precise economic invested-capital return calculation.
    """
    p = dict(inputs)
    n_raw = p.get("yillar")
    if isinstance(n_raw, bool) or not isinstance(n_raw, int) or not (1 <= n_raw <= 40):
        raise ValueError("yillar: integer 1..40 required")
    n = n_raw
    base = _num(p["gelir_0"], "gelir_0")
    r = _num(p["iskonto"], "iskonto")
    g_terminal = _num(p["uc_buyume"], "uc_buyume")
    g_cap = _num(p.get("uc_buyume_tavani", .04), "uc_buyume_tavani")
    ron = _num(p["uc_roic"], "uc_roic")
    shares = _num(p["hisse"], "hisse")
    debt = _num(p.get("net_borc", 0), "net_borc")
    tax_rate = _num(p["vergi_orani"], "vergi_orani")
    loss = _num(p.get("baslangic_zarar", 0), "baslangic_zarar")
    initial_margin = _num(p["marj_0"], "marj_0")
    margin_target = _num(p["marj_hedef"], "marj_hedef")
    convergence = _num(p["yakinlasma"], "yakinlasma")
    timing = p.get("iskonto_zamani", "yil_sonu")
    in_margin = p.get("sbc_marjda_dahil", True)
    sbc = _num(p.get("sbc_ilave_gider_orani", 0), "sbc_ilave_gider_orani")
    if base <= 0 or shares <= 0 or r <= 0 or ron <= 0:
        raise ValueError("revenue, shares, discount rate and terminal RONIC must be positive")
    if not (0 <= tax_rate < 1) or loss < 0:
        raise ValueError("invalid tax rate or opening tax loss")
    if not (0 <= convergence <= 1):
        raise ValueError("yakinlasma must be in [0,1]")
    if not (-1 <= initial_margin <= 1 and -1 <= margin_target <= 1):
        raise ValueError("margins must be in [-1,1]")
    if g_terminal >= r or g_terminal > g_cap or g_terminal <= -1:
        raise ValueError("terminal growth must be > -100%, below discount and within cap")
    if timing not in ("yil_sonu", "yil_ortasi"):
        raise ValueError("invalid discount timing")
    if not isinstance(in_margin, bool) or sbc < 0 or sbc > 1:
        raise ValueError("invalid SBC bookkeeping")
    if in_margin and sbc != 0:
        raise ValueError("SBC double counting: expense already in margin")
    if p.get("sbc_yontemi", "gider") != "gider":
        raise ValueError("v0.2 supports expense SBC only")
    growth = _series(p["buyume"], n, "buyume")
    sales_to_capital = _series(p["satis_sermaye"], n, "satis_sermaye")
    if any(g <= -1 for g in growth) or any(sc <= 0 for sc in sales_to_capital):
        raise ValueError("annual growth must exceed -100% and sales/capital be positive")
    margin_path = p.get("marj_yolu")
    if margin_path is not None:
        margin_path = _series(margin_path, n, "marj_yolu")
        if any(not -1 <= m <= 1 for m in margin_path):
            raise ValueError("marj_yolu margins must be in [-1,1]")

    revenue = base
    rows = []
    present_operating = 0.0
    warnings = []
    previous_nopat = None
    previous_reinvestment = None
    for year, (g, sc) in enumerate(zip(growth, sales_to_capital), start=1):
        new_revenue = revenue * (1 + g)
        if margin_path is not None:
            margin = margin_path[year - 1]
        else:
            margin = margin_target + (initial_margin - margin_target) * (1-convergence)**year
        ebit = new_revenue * (margin - (0 if in_margin else sbc))
        loss_used = 0.0
        if ebit < 0:
            loss += -ebit
            cash_tax = 0.0
        else:
            loss_used = min(loss, ebit)
            loss -= loss_used
            cash_tax = (ebit-loss_used) * tax_rate
        nopat = ebit - cash_tax
        reinvestment = (new_revenue - revenue) / sc
        fcff = nopat - reinvestment
        exponent = year - (0.5 if timing == "yil_ortasi" else 0)
        discount = (1+r)**(-exponent)
        present_operating += fcff*discount
        roiic = None
        if previous_nopat is not None and previous_reinvestment is not None and previous_reinvestment > 0:
            roiic = (nopat - previous_nopat)/previous_reinvestment
        rows.append({"yil": year, "gelir": new_revenue, "faaliyet_marji": margin,
                     "ebit": ebit, "kullanilan_zarar": loss_used,
                     "kalan_zarar": loss, "nakit_vergi": cash_tax,
                     "nopat": nopat, "yeniden_yatirim": reinvestment,
                     "fcff": fcff, "roiic": roiic,
                     "iskonto_faktoru": discount, "bugunku_deger": fcff*discount})
        previous_nopat, previous_reinvestment = nopat, reinvestment
        revenue = new_revenue
    # Terminal cash taxes are NORMALIZED. Finite forecast NOL is not extrapolated forever.
    terminal_ebit = revenue*(1+g_terminal)*(margin - (0 if in_margin else sbc))
    terminal_nopat = terminal_ebit * (1-tax_rate) if terminal_ebit >= 0 else terminal_ebit
    terminal_reinvestment = terminal_nopat * (g_terminal / ron)
    terminal_fcff = terminal_nopat - terminal_reinvestment
    tv = terminal_fcff/(r-g_terminal)
    # Discounted at n even with yil_ortasi (a common, conservative convention).
    # Shifting it to n-0.5 as well would raise value by a factor of (1+r)**0.5.
    terminal_pv = tv/(1+r)**n
    enterprise = present_operating + terminal_pv
    equity = enterprise - debt
    tv_share = terminal_pv/enterprise if enterprise > 0 else None
    if tv_share is not None and tv_share > .85:
        warnings.append("UC_DEGER_BASKIN")
    if ron < r and g_terminal > 0:
        warnings.append("UC_ROIC_ISKONTO_ALTINDA")
    if ron > r*1.25 and not p.get("kalici_rekabet_avantaji", False):
        warnings.append("UC_ROIC_YUKSEK_KANIT_GEREKLI")
    if loss > 0:
        warnings.append("UC_VERGI_NORMALIZE_EDILDI")
    if any(row["yeniden_yatirim"] < 0 for row in rows):
        warnings.append("NEGATIF_YATIRIM_SERMAYE_CIKISI_VARSAYIMI")
    if any(row["fcff"] < 0 for row in rows):
        warnings.append("NEGATIF_FCFF_YILLARI")
    if equity < 0:
        warnings.append("OZSERMAYE_NEGATIF")
    result = {"durum": "gecerli", "motor_surumu": VERSION,
              "tablo": rows, "acik_donem_bd": present_operating,
              "uc_deger": tv, "uc_deger_bd": terminal_pv,
              "uc_nopat_normalize": terminal_nopat,
              "uc_yeniden_yatirim": terminal_reinvestment,
              "firma_degeri": enterprise, "ozsermaye_degeri": equity,
              "hisse_basi_deger": equity/shares, "uc_deger_payi": tv_share,
              "uyarilar": warnings,
              "sinirlar": ["no SBC dilution", "tax losses simplified: no expiry or jurisdictional restrictions", "terminal normalized cash taxes", "margin convergence is not explicitly tied to growth"]}
    if not all(math.isfinite(x) for x in (present_operating, terminal_pv, enterprise, equity)):
        raise ValueError("non-finite valuation output")
    return result

def ters_dcf_v02(inputs, price, lower=-0.5, upper=1.0, grid_steps=4096):
    """Explore price-implied constant growth without a completeness guarantee.

    Each detected candidate is checked against the DCF valuation. Finite
    grid sampling cannot prove there are no additional roots.
    """
    from dogrulama.moduller_v02 import tum_kokler
    price = _num(price, "price")
    lower = _num(lower, "lower")
    upper = _num(upper, "upper")
    if price <= 0 or not (-1 < lower < upper) or grid_steps < 3:
        raise ValueError("invalid price, growth bounds or grid steps")
    degerle_v02(dict(inputs, buyume=lower))
    def residual(rate):
        value = degerle_v02(dict(inputs, buyume=rate))
        return value["hisse_basi_deger"] - price
    candidates = tum_kokler(residual, lower, upper, adim=grid_steps,
                            x_tol=1e-10, y_tol=max(1e-9, abs(price)*1e-10))
    tolerance = max(1e-6, abs(price)*1e-7)
    verified = []
    for rate in candidates:
        difference = residual(rate)
        if math.isfinite(difference) and abs(difference) <= tolerance:
            verified.append({"buyume": rate, "fiyat_farki": difference})
    state = ("tek_cozum_dogrulandi" if len(verified) == 1 else
             "coklu_cozum_dogrulandi" if verified else "cozum_dogrulanamadi")
    return {"durum": state, "fiyat": price,
            "ima_edilen_buyume": verified[0]["buyume"] if len(verified) == 1 else None,
            "dogrulanan_kokler": verified,
            "arama_araligi": [lower, upper], "adim": grid_steps,
            "tum_kokler_bulundu_garantisi": False,
            "aciklama": "Grid, sign-change bisection and tangent heuristic; absence of candidates is not proof of no roots."}
