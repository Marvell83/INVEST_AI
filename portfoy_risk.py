"""INVEST_AI portfolio concentration and user-defined stress-test engine.

Point-in-time USD holdings, with fractional shares and optional current USD/TRY
translation. No data download, forecast, implicit target weights, or sell advice.
"""
from __future__ import annotations

import argparse
import datetime as dt
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path
import re

VERSION = "invest-ai-portfolio-0.1"
CENTS = Decimal("0.01")
FOUR = Decimal("0.0001")
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")
LABEL_RE = re.compile(r"^[a-z][a-z0-9_]{1,49}$")


def _num(value, name, *, allow_zero=True):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"{name}: numeric value required")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{name}: invalid number") from exc
    if not result.is_finite() or result < 0 or (not allow_zero and result == 0):
        raise ValueError(f"{name}: finite {'nonnegative' if allow_zero else 'positive'} number required")
    return result


def _date(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{name}: ISO YYYY-MM-DD date required")
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name}: invalid date") from exc


def _money(value):
    return float(value.quantize(CENTS, rounding=ROUND_HALF_UP))


def _pct(value):
    return float((value * 100).quantize(FOUR, rounding=ROUND_HALF_UP))


def _ensure_name(value, field):
    if not isinstance(value, str) or not LABEL_RE.fullmatch(value):
        raise ValueError(f"{field}: lowercase snake_case label required")
    return value


def analyze_portfolio(raw):
    if not isinstance(raw, dict) or raw.get("schema_version") != VERSION:
        raise ValueError("unsupported portfolio schema")
    if raw.get("base_currency") != "USD":
        raise ValueError("only USD base currency is supported")
    as_of = _date(raw.get("as_of"), "as_of")
    items = raw.get("positions")
    if not isinstance(items, list) or not 1 <= len(items) <= 1000:
        raise ValueError("positions must contain 1..1000 holdings")
    cash = _num(raw.get("cash_usd", 0), "cash_usd")
    saved = []
    unique = set()
    warnings = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"positions[{i}]: object required")
        ticker = item.get("ticker")
        if not isinstance(ticker, str) or not TICKER_RE.fullmatch(ticker):
            raise ValueError(f"positions[{i}]: invalid ticker")
        if ticker in unique:
            raise ValueError(f"duplicate ticker: {ticker}; aggregate lots before analysis")
        unique.add(ticker)
        quantity = _num(item.get("quantity"), f"{ticker}.quantity", allow_zero=False)
        price = _num(item.get("price_usd"), f"{ticker}.price_usd", allow_zero=False)
        quote_date = _date(item.get("price_date"), f"{ticker}.price_date")
        if quote_date > as_of:
            raise ValueError(f"{ticker}: quote is later than research cutoff")
        age = (as_of - quote_date).days
        if age > 7:
            warnings.append(f"{ticker}: price is {age} days old")
        cost = (None if item.get("cost_per_share_usd") is None else
                _num(item["cost_per_share_usd"], f"{ticker}.cost_per_share_usd"))
        kind = item.get("instrument_type", "equity")
        if kind not in ("equity", "fund"):
            raise ValueError(f"{ticker}: instrument_type must be equity or fund")
        sector = item.get("sector")
        if sector is None:
            sector = "unclassified"
        else:
            _ensure_name(sector, f"{ticker}.sector")
        labels = item.get("themes")
        if labels is None:
            warnings.append(f"{ticker}: thematic classification not provided")
            labels = []
        if not isinstance(labels, list) or len(labels) != len(set(map(str, labels))):
            raise ValueError(f"{ticker}: themes must be a nonduplicate list")
        for label in labels:
            _ensure_name(label, f"{ticker}.theme")
        mv = price * quantity
        cb = None if cost is None else cost * quantity
        quote_source = item.get("price_source")
        if quote_source is not None and (not isinstance(quote_source, str) or not quote_source.strip()):
            raise ValueError(f"{ticker}: invalid price_source")
        if quote_source is None:
            warnings.append(f"{ticker}: user-supplied price not independently verified")
        if kind == "fund":
            warnings.append(f"{ticker}: fund constituents are not decomposed into underlying holdings")
        saved.append({
            "ticker": ticker, "quantity": str(quantity), "price_usd": _money(price),
            "price_date": quote_date.isoformat(), "price_age_days": age,
            "price_source": quote_source, "instrument_type": kind,
            "sector": sector, "themes": sorted(labels),
            "market_value_exact": mv, "cost_exact": cb,
        })

    invested = sum((x["market_value_exact"] for x in saved), Decimal(0))
    total = invested + cash
    by_sector = {}
    by_theme = {}
    for p in saved:
        by_sector[p["sector"]] = by_sector.get(p["sector"], Decimal(0)) + p["market_value_exact"]
        for tag in p["themes"]:
            by_theme[tag] = by_theme.get(tag, Decimal(0)) + p["market_value_exact"]
    saved.sort(key=lambda x: (-x["market_value_exact"], x["ticker"]))
    hhi = sum(((x["market_value_exact"] / invested) ** 2 for x in saved), Decimal(0))
    known_cost = all(x["cost_exact"] is not None for x in saved)
    cost_total = sum((x["cost_exact"] for x in saved), Decimal(0)) if known_cost else None
    result_positions = []
    for p in saved:
        basis = p["cost_exact"]
        result_positions.append({
            "ticker": p["ticker"], "quantity": p["quantity"],
            "price_usd": p["price_usd"], "price_date": p["price_date"],
            "price_age_days": p["price_age_days"], "price_source": p["price_source"],
            "instrument_type": p["instrument_type"],
            "sector": p["sector"], "themes": p["themes"],
            "market_value_usd": _money(p["market_value_exact"]),
            "cost_basis_usd": None if basis is None else _money(basis),
            "unrealized_pnl_usd": None if basis is None else _money(p["market_value_exact"] - basis),
            "unrealized_return_pct": None if basis is None or basis == 0 else
                                     _pct((p["market_value_exact"] - basis) / basis),
            "weight_total_pct": _pct(p["market_value_exact"] / total),
            "weight_invested_pct": _pct(p["market_value_exact"] / invested),
        })
    def allocation(m):
        return [{
            "label": key,
            "market_value_usd": _money(value),
            "weight_total_pct": _pct(value / total),
            "weight_invested_pct": _pct(value / invested),
        } for key, value in sorted(m.items(), key=lambda x: (-x[1], x[0]))]

    unions = raw.get("theme_unions", {})
    if not isinstance(unions, dict):
        raise ValueError("theme_unions must be an object")
    union_reports = []
    for label, member_tags in sorted(unions.items()):
        _ensure_name(label, "theme_union")
        if (not isinstance(member_tags, list) or not member_tags or
                len(member_tags) != len(set(map(str, member_tags)))):
            raise ValueError(f"{label}: unique nonempty tag list required")
        for tag in member_tags:
            _ensure_name(tag, f"{label}.member_tag")
            if tag not in by_theme:
                raise ValueError(f"{label}: unknown theme tag {tag}; check classification")
        included = [p for p in saved if set(p["themes"]).intersection(member_tags)]
        value = sum((p["market_value_exact"] for p in included), Decimal(0))
        union_reports.append({
            "label": label, "member_tags": sorted(member_tags),
            "tickers": sorted(p["ticker"] for p in included),
            "market_value_usd": _money(value),
            "weight_total_pct": _pct(value / total),
            "weight_invested_pct": _pct(value / invested),
            "method": "union of user-provided tags; each holding counted once",
        })

    scenarios = raw.get("scenarios", [])
    if not isinstance(scenarios, list):
        raise ValueError("scenarios must be a list")
    scenario_results = []
    seen_scenario_names = set()
    for idx, scen in enumerate(scenarios):
        if not isinstance(scen, dict):
            raise ValueError(f"scenarios[{idx}]: object required")
        name = _ensure_name(scen.get("name"), "scenario.name")
        if name in seen_scenario_names:
            raise ValueError(f"duplicate scenario {name}")
        seen_scenario_names.add(name)
        horizon = scen.get("horizon")
        explanation = scen.get("rationale")
        if not isinstance(horizon, str) or not horizon.strip() or not isinstance(explanation, str) or not explanation.strip():
            raise ValueError(f"{name}: explicit horizon and rationale required")
        shocks = scen.get("shocks_pct")
        if not isinstance(shocks, dict) or set(shocks) != unique:
            raise ValueError(f"{name}: specify shock percentages for EVERY position; no assumed zeros")
        by_holding = []
        impact = Decimal(0)
        for p in saved:
            ticker = p["ticker"]
            try:
                shock_pct = (Decimal(str(shocks[ticker]))
                             if not isinstance(shocks[ticker], bool) else Decimal("NaN"))
            except (InvalidOperation, ValueError, TypeError) as exc:
                raise ValueError(f"{name}.{ticker}: invalid scenario shock") from exc
            if not shock_pct.is_finite() or shock_pct < -100:
                raise ValueError(f"{name}.{ticker}: shock must be >= -100% and finite")
            delta = p["market_value_exact"] * shock_pct / 100
            impact += delta
            by_holding.append({"ticker": ticker, "shock_pct": _pct(shock_pct / 100),
                               "impact_usd": _money(delta)})
        scenario_results.append({
            "name": name, "horizon": horizon, "rationale": explanation,
            "assumption_type": "user_supplied_hypothetical_not_a_forecast",
            "impact_usd": _money(impact), "portfolio_return_pct": _pct(impact / total),
            "post_stress_value_usd": _money(total + impact),
            "cash_unchanged_usd": _money(cash), "by_position": by_holding,
        })

    fx = raw.get("fx_usdtry")
    tl = None
    if fx is not None:
        if not isinstance(fx, dict):
            raise ValueError("fx_usdtry must be an object")
        rate = _num(fx.get("rate"), "fx_usdtry.rate", allow_zero=False)
        date = _date(fx.get("date"), "fx_usdtry.date")
        if date > as_of:
            raise ValueError("FX quote is later than cutoff")
        if (as_of - date).days > 7:
            warnings.append("USD/TRY rate older than seven days")
        tl = {"rate": float(rate), "date": date.isoformat(),
              "total_market_value_try": _money(total * rate),
              "invested_value_try": _money(invested * rate),
              "notice": "Current TL translation ONLY. Historical TRY cost and FX-adjusted TRY P&L are not calculated."}

    return {
        "schema_version": VERSION, "as_of": as_of.isoformat(), "base_currency": "USD",
        "status": "ANALYSIS_FROM_USER_INPUTS",
        "price_verification": "not_independently_verified",
        "positions": result_positions,
        "total_market_value_usd": _money(total),
        "invested_market_value_usd": _money(invested),
        "cash_usd": _money(cash), "cash_weight_pct": _pct(cash / total),
        "unrealized_pnl_usd": None if cost_total is None else _money(invested - cost_total),
        "known_cost_basis_for_all_positions": known_cost,
        "largest_holding_pct_of_invested": _pct(saved[0]["market_value_exact"] / invested),
        "top_three_pct_of_invested": _pct(sum((x["market_value_exact"] for x in saved[:3]), Decimal(0)) / invested),
        "hhi_invested": float(hhi.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)),
        "effective_number_of_positions": float((1 / hhi).quantize(CENTS, rounding=ROUND_HALF_UP)),
        "sector_allocation": allocation(by_sector),
        "theme_exposures": allocation(by_theme),
        "theme_unions": union_reports,
        "theme_coverage_pct_of_invested": _pct(sum((p["market_value_exact"] for p in saved if p["themes"]), Decimal(0)) / invested),
        "scenarios": scenario_results,
        "fx_usdtry": tl,
        "warnings": sorted(set(warnings)),
        "limitations": [
            "No live prices, factor betas, historical correlations or implied trading advice",
            "Sectors and themes are manually classified, not independently verified",
            "Overlapping theme percentages must not be summed; use the deduplicated unions",
            "ETF constituent look-through is NOT computed",
            "Scenario shocks are hypothetical and are NOT probability-weighted forecasts",
            "HHI and effective count describe position concentration, not independent economic risk",
            "USD holdings are long-only; fees, dividends, taxes and historical TRY cost are excluded",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="INVEST_AI USD portfolio concentration and scenario risk")
    parser.add_argument("--portfolio", required=True, help="positions, quotes, tags and optional scenarios JSON")
    parser.add_argument("--out", required=True)
    options = parser.parse_args(argv)
    raw = json.loads(Path(options.portfolio).read_text(encoding="utf-8"),
                     parse_constant=lambda x: (_ for _ in ()).throw(ValueError("nonfinite JSON number")))
    result = analyze_portfolio(raw)
    target = Path(options.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False),
                      encoding="utf-8")
    print(f"{len(result['positions'])} holdings | USD {result['total_market_value_usd']:.2f} | {target}")


if __name__ == "__main__":
    main()
