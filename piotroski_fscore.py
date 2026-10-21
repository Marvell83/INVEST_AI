"""Point-in-time conservative Piotroski F-Score from SEC US-GAAP Company Facts.

No false zero for missing data. No score for an unconfirmed/financial sector.
Stock splits do NOT imply issuance; offering evidence is manual.
Independent of credit ratings and DCF.
"""
from __future__ import annotations
import datetime as dt
import math
from sec_companyfacts import METRICS, _date, _validate_cik, SEC_DATA, FORMS

VERSION = "piotroski-sec-0.2.0"
FLOW = {
    "revenue": METRICS["revenue"],
    "ni": ("NetIncomeLoss",),
    "cfo": ("NetCashProvidedByUsedInOperatingActivities",),
    "gp": ("GrossProfit",),
}
INSTANT = {
    "assets": ("Assets",),
    "ca": ("AssetsCurrent",),
    "cl": ("LiabilitiesCurrent",),
    "debt": ("LongTermDebtNoncurrent", "LongTermDebt"),
}
NAMES = ("ROA_POSITIVE", "CFO_POSITIVE", "DELTA_ROA", "QUALITY_OF_EARNINGS",
         "DELTA_LEVERAGE", "DELTA_LIQUIDITY", "NO_EQUITY_OFFERING",
         "DELTA_GROSS_MARGIN", "DELTA_ASSET_TURNOVER")

def _number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and abs(x)<1e30

def _series(data, tag, as_of, instant):
    facts = data.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {}).get("USD", [])
    selected = {}
    for row in facts:
        if row.get("form") not in FORMS or row.get("fp") != "FY":
            continue
        try:
            end, filed = _date(row.get("end")), _date(row.get("filed"))
            start = None if instant else _date(row.get("start"))
        except ValueError:
            continue
        if end > as_of or filed > as_of or not row.get("accn") or not _number(row.get("val")):
            continue
        if not instant and not 330 <= (end-start).days+1 <= 400:
            continue
        f = {"value_usd": float(row["val"]), "end": end.isoformat(),
             "start": None if instant else start.isoformat(), "filed": filed.isoformat(),
             "accession": row["accn"], "form": row["form"], "concept": tag,
             "source": SEC_DATA.format(cik=int(data["cik"]))}
        prev = selected.get(f["end"])
        if prev is None or (f["filed"],f["form"]=="10-K/A",f["accession"])>(prev["filed"],prev["form"]=="10-K/A",prev["accession"]):
            selected[f["end"]] = f
    return selected

def _pick(data, tags, as_of, end, instant):
    facts = [_series(data, tag, as_of, instant).get(end) for tag in tags]
    facts = [f for f in facts if f is not None]
    if not facts:
        return None, "MISSING"
    values = [f["value_usd"] for f in facts]
    peak = max(abs(v) for v in values)
    if peak and (max(values)-min(values))/peak > .05:
        return None, "CONFLICTING_ALIASES"
    return facts[0], None


def _derived_gross_profit(data, as_of, end, revenue):
    """Derived revenue less cost only for the same SEC fiscal period and filing."""
    if revenue is None:
        return None, "REVENUE_REQUIRED_FOR_GROSS_PROFIT"
    costs = []
    for tag in ("CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"):
        f = _series(data, tag, as_of, False).get(end)
        if f and f["start"] == revenue["start"] and f["accession"] == revenue["accession"]:
            costs.append(f)
    if not costs:
        return None, "MATCHED_COST_OF_REVENUE_MISSING"
    amounts = [f["value_usd"] for f in costs]
    scale = max(abs(v) for v in amounts)
    if scale and (max(amounts) - min(amounts)) / scale > .005:
        return None, "CONFLICTING_COST_OF_REVENUE_ALIASES"
    cost = costs[0]
    if cost["value_usd"] < 0 or revenue["value_usd"] <= 0:
        return None, "NONPOSITIVE_REVENUE_OR_NEGATIVE_COST"
    result = dict(revenue)
    result.update(concept="DERIVED_GROSS_PROFIT",
                  value_usd=revenue["value_usd"] - cost["value_usd"],
                  method="REVENUE_MINUS_MATCHED_COST",
                  derivation={"revenue": revenue, "cost": cost})
    return result, None


def _noncurrent_debt(data, as_of, end):
    """Never substitute total long-term debt for noncurrent debt.

    If direct noncurrent debt is absent, derive total debt less current maturities
    only when both components refer to the same SEC accession and FY end.
    """
    direct = _series(data, "LongTermDebtNoncurrent", as_of, True).get(end)
    total = _series(data, "LongTermDebt", as_of, True).get(end)
    current = _series(data, "LongTermDebtCurrent", as_of, True).get(end)
    derived = None
    if total and current and total["accession"] == current["accession"]:
        if 0 <= current["value_usd"] <= total["value_usd"]:
            derived = dict(total)
            derived.update(concept="DERIVED_LONG_TERM_DEBT_NONCURRENT",
                           value_usd=total["value_usd"]-current["value_usd"],
                           method="TOTAL_LONG_TERM_DEBT_MINUS_CURRENT_PORTION",
                           derivation={"total": total, "current": current})
    if direct:
        if direct["value_usd"] < 0:
            return None, "NEGATIVE_NONCURRENT_DEBT"
        if derived and direct["accession"] == derived["accession"]:
            a, b = direct["value_usd"], derived["value_usd"]
            if max(abs(a), abs(b)) and abs(a-b)/max(abs(a), abs(b)) > .005:
                return None, "NONCURRENT_DEBT_RECONCILIATION_CONFLICT"
        return direct, None
    if derived:
        return derived, None
    if total is not None and current is None:
        return None, "LONG_TERM_DEBT_TOTAL_WITHOUT_CURRENT_COMPONENT"
    if total is not None and current is not None:
        return None, "DEBT_COMPONENTS_INCONSISTENT_OR_FILING_MISMATCH"
    return None, "NONCURRENT_DEBT_MISSING"


def _previous(dates, anchor):
    if not anchor: return None
    d = dt.date.fromisoformat(anchor)
    candidates = [x for x in dates if 330 <= (d-dt.date.fromisoformat(x)).days <= 400]
    return candidates[0] if len(candidates)==1 else None

def _div(x,y):
    return x/y if x is not None and y is not None and y>0 else None

def _manual_offering(evidence, as_of, start, end):
    if not isinstance(evidence, dict) or not isinstance(evidence.get("issued"), bool):
        return None
    if evidence.get("fiscal_start")!=start or evidence.get("fiscal_end")!=end:
        return None
    if not isinstance(evidence.get("source_url"), str) or not evidence["source_url"].startswith("https://"):
        return None
    if not isinstance(evidence.get("review_note"), str) or len(evidence["review_note"].strip())<12:
        return None
    try: reviewed = _date(evidence["reviewed_at"])
    except (ValueError,KeyError): return None
    if reviewed>as_of or reviewed<dt.date.fromisoformat(start):
        return None
    return int(not evidence["issued"])

def compute_piotroski(companyfacts, *, as_of, sector="unknown", equity_offering_evidence=None):
    cutoff = _date(as_of)
    if not isinstance(companyfacts,dict) or not isinstance(companyfacts.get("facts"),dict):
        raise ValueError("raw SEC Company Facts object required")
    cik = _validate_cik(companyfacts.get("cik"))
    if sector not in ("non_financial","financial","unknown"):
        raise ValueError("sector must be non_financial, financial or unknown")
    result = {"version":VERSION,"company":companyfacts.get("entityName",""),
              "cik":f"{cik:010d}","as_of":as_of,"sector":sector,
              "signals":dict.fromkeys(NAMES),"known_count":0,"missing_count":9,
              "score":None,"score_range":[0,9],"status":"partial",
              "missing_reasons":{},"periods":{},"provenance":{},
              "warnings":["USD US-GAAP annual 10-K / 10-K/A only; no equity recommendation"]}
    if sector!="non_financial":
        result["status"]="not_applicable_financial_sector" if sector=="financial" else "sector_unconfirmed"
        result["warnings"].append("Industry-specific evaluation required; no Piotroski score")
        return result

    ni_dates = _series(companyfacts,"NetIncomeLoss",cutoff,False)
    dates = sorted(ni_dates,reverse=True)
    current = dates[0] if dates else None
    prior = _previous(dates,current)
    asset_dates = _series(companyfacts,"Assets",cutoff,True)
    opening = _previous(list(asset_dates),prior)
    result["periods"]={"current_fy_end":current,"prior_fy_end":prior,"opening_assets_end":opening}
    if not current or not prior:
        result["missing_reasons"]={name:"TWO_COMPARABLE_ANNUAL_INCOME_PERIODS_REQUIRED" for name in NAMES}
        return result

    columns = {
        "ni_t":("ni",current,False),"ni_p":("ni",prior,False),
        "cfo_t":("cfo",current,False),
        "rev_t":("revenue",current,False),"rev_p":("revenue",prior,False),
        "gp_t":("gp",current,False),"gp_p":("gp",prior,False),
        "a_t":("assets",current,True),"a_p":("assets",prior,True),
        "a_o":("assets",opening,True),
        "d_t":("debt",current,True),"d_p":("debt",prior,True),
        "ca_t":("ca",current,True),"ca_p":("ca",prior,True),
        "cl_t":("cl",current,True),"cl_p":("cl",prior,True)}
    values={};issues={}
    for key,(kind,end,instant) in columns.items():
        if end is None:
            values[key]=None;issues[key]="PRIOR_ASSET_PERIOD_MISSING"
            continue
        if kind == "debt":
            fact,reason = _noncurrent_debt(companyfacts,cutoff,end)
        else:
            fact,reason = _pick(companyfacts,(INSTANT if instant else FLOW)[kind],cutoff,end,instant)
        if kind == "gp" and fact is None and reason == "MISSING":
            revenue_key = "rev_t" if key == "gp_t" else "rev_p"
            revenue_fact = result["provenance"].get(revenue_key)
            if revenue_fact is not None:
                fact,reason = _derived_gross_profit(companyfacts,cutoff,end,revenue_fact)
        values[key]=fact["value_usd"] if fact else None
        if reason: issues[key]=reason
        if fact: result["provenance"][key]=fact
    # Reject mismatched fiscal start dates, not just year-end mismatches.
    for key,anchor in (("cfo_t","ni_t"),("rev_t","ni_t"),
                       ("gp_t","ni_t"),("rev_p","ni_p"),("gp_p","ni_p")):
        fact = result["provenance"].get(key)
        base = result["provenance"].get(anchor)
        if not fact or not base or fact["start"]!=base["start"]:
            values[key]=None
            issues[key]=issues.get(key) or "FISCAL_START_MISMATCH_OR_MISSING"
    def v(key): return values.get(key)
    def avg(x,y):
        a,b=v(x),v(y)
        return (a+b)/2 if a is not None and b is not None and a>0 and b>0 else None
    roa=_div(v("ni_t"),v("a_p"));prev_roa=_div(v("ni_p"),v("a_o"))
    lm=_div(v("d_t"),avg("a_t","a_p"));lp=_div(v("d_p"),avg("a_p","a_o"))
    liquid=_div(v("ca_t"),v("cl_t"));prev_liquid=_div(v("ca_p"),v("cl_p"))
    margin=_div(v("gp_t"),v("rev_t"));prev_margin=_div(v("gp_p"),v("rev_p"))
    turnover=_div(v("rev_t"),avg("a_t","a_p"));prev_turnover=_div(v("rev_p"),avg("a_p","a_o"))
    def paired(x,y,predicate):
        return int(predicate(x,y)) if x is not None and y is not None else None
    signals={
        "ROA_POSITIVE":int(roa>0) if roa is not None else None,
        "CFO_POSITIVE":int(v("cfo_t")>0) if v("cfo_t") is not None else None,
        "DELTA_ROA":paired(roa,prev_roa,lambda a,b:a>b),
        "QUALITY_OF_EARNINGS":paired(v("cfo_t"),v("ni_t"),lambda a,b:a>b),
        "DELTA_LEVERAGE":paired(lm,lp,lambda a,b:(a<b and not math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12)) or (a==0 and b==0)),
        "DELTA_LIQUIDITY":paired(liquid,prev_liquid,lambda a,b:a>b),
        "NO_EQUITY_OFFERING":_manual_offering(equity_offering_evidence,cutoff,ni_dates[current]["start"],current),
        "DELTA_GROSS_MARGIN":paired(margin,prev_margin,lambda a,b:a>b),
        "DELTA_ASSET_TURNOVER":paired(turnover,prev_turnover,lambda a,b:a>b)}
    deps={
        "ROA_POSITIVE":("ni_t","a_p"),"CFO_POSITIVE":("cfo_t",),
        "DELTA_ROA":("ni_t","a_p","ni_p","a_o"),
        "QUALITY_OF_EARNINGS":("cfo_t","ni_t"),
        "DELTA_LEVERAGE":("d_t","d_p","a_t","a_p","a_o"),
        "DELTA_LIQUIDITY":("ca_t","ca_p","cl_t","cl_p"),
        "DELTA_GROSS_MARGIN":("gp_t","gp_p","rev_t","rev_p"),
        "DELTA_ASSET_TURNOVER":("rev_t","rev_p","a_t","a_p","a_o")}
    result["signals"]=signals
    for name,s in signals.items():
        if s is None:
            if name=="NO_EQUITY_OFFERING":
                reason="Dated source-backed human equity issuance/no-issuance review required"
            else:
                blockers=[f"{k}:{issues.get(k,'MISSING_OR_INVALID_DENOMINATOR')}"
                          for k in deps[name] if v(k) is None or k in issues]
                reason=",".join(blockers) or "INVALID_DENOMINATOR_OR_MISSING"
            result["missing_reasons"][name]=reason
    known=[x for x in signals.values() if x is not None]
    lower=sum(known)
    result.update(known_count=len(known),missing_count=9-len(known),
                  score=lower if len(known)==9 else None,
                  score_range=[lower,lower+9-len(known)],
                  status="complete" if len(known)==9 else "partial")
    result["diagnostics"]={"roa":roa,"prior_roa":prev_roa,
                           "gross_margin":margin,"prior_gross_margin":prev_margin,
                           "asset_turnover":turnover,"prior_asset_turnover":prev_turnover,
                           "leverage":lm,"prior_leverage":lp,
                           "current_ratio":liquid,"prior_current_ratio":prev_liquid}
    if any(f.get("method") in ("REVENUE_MINUS_MATCHED_COST", "TOTAL_LONG_TERM_DEBT_MINUS_CURRENT_PORTION") for f in result["provenance"].values()):
        result["warnings"].append("Derived SEC facts are same-filing arithmetic, not manually verified consolidated statement totals")
    result["warnings"].append("Piotroski is a screening signal, not fair value; originally tested with high book-to-market firms")
    return result
