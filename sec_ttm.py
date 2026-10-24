"""Offline SEC US-GAAP USD trailing twelve month financial flows.

TTM = previous FY + current fiscal YTD - comparable prior-year fiscal YTD.
No estimated quarters, conversion, FCFF, or invented accounting values.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
from pathlib import Path
from sec_companyfacts import _date, _validate_cik, SEC_DATA, METRICS

VERSION="sec-ttm-0.1.0"
FLOW_TAGS={"revenue":METRICS["revenue"],
           "ebit":("OperatingIncomeLoss",),
           "cfo":("NetCashProvidedByUsedInOperatingActivities",),
           "capex":("PaymentsToAcquirePropertyPlantAndEquipment",)}
ANNUAL_FORMS=frozenset(("10-K","10-K/A"))
INTERIM_FORMS=frozenset(("10-Q","10-Q/A"))


def _facts(raw,metric,cutoff,forms):
    result=[]
    for tag in FLOW_TAGS[metric]:
        rows=raw.get("facts",{}).get("us-gaap",{}).get(tag,{}).get("units",{}).get("USD",[])
        for r in rows:
            if r.get("form") not in forms or not isinstance(r.get("accn"),str) or not r["accn"]:
                continue
            try:
                start,end,filed=(_date(r[k]) for k in ("start","end","filed"))
            except (KeyError,ValueError,TypeError):
                continue
            value=r.get("val")
            if (isinstance(value,bool) or not isinstance(value,(int,float)) or
                not math.isfinite(value) or abs(value)>=1e30 or start>end or end>cutoff or filed>cutoff):
                continue
            result.append({"value_usd":value,"start":start.isoformat(),
                           "end":end.isoformat(),"filed":filed.isoformat(),
                           "accession":r["accn"],"form":r["form"],"concept":tag})
    return result


def _choose(candidates,metric,component,tolerance=.005):
    if not candidates:
        raise ValueError(f"{metric}/{component}: missing comparable SEC fact")
    selected=[]
    for tag in FLOW_TAGS[metric]:
        choices=[r for r in candidates if r["concept"]==tag]
        if choices:
            selected.append(max(choices,key=lambda r:(r["filed"],r["form"].endswith("/A"),r["accession"])))
    values=[r["value_usd"] for r in selected]
    spread=max(values)-min(values)
    scale=max(1,*(abs(v) for v in values))
    if spread>tolerance*scale:
        raise ValueError(f"{metric}/{component}: inconsistent XBRL concept values; manual review")
    return selected[0]


def compute_ttm(raw,*,as_of,current_ytd_end,prior_fy_end=None,
                metrics=("revenue","ebit","cfo","capex")):
    cutoff,current_end=_date(as_of),_date(current_ytd_end)
    if current_end>cutoff or not isinstance(raw,dict):
        raise ValueError("current quarter end must not exceed knowledge cutoff")
    cik=_validate_cik(raw.get("cik"))
    if (not isinstance(metrics,(list,tuple)) or not metrics or
        any(m not in FLOW_TAGS for m in metrics) or len(set(metrics))!=len(metrics)):
        raise ValueError("invalid or duplicate flow metric")
    annual_candidates=_facts(raw,"revenue",cutoff,ANNUAL_FORMS)
    if prior_fy_end:
        previous_end=_date(prior_fy_end)
    else:
        eligible=sorted({_date(x["end"]) for x in annual_candidates
                         if 1 <= (current_end-_date(x["end"])).days <= 310},reverse=True)
        if len(eligible)!=1:
            raise ValueError("ambiguous previous fiscal-year end; specify prior_fy_end")
        previous_end=eligible[0]
    current_start=previous_end+dt.timedelta(days=1)
    current_span=(current_end-current_start).days+1
    if not 75<=current_span<=310:
        raise ValueError("YTD interval must span one to three fiscal quarters")
    url=SEC_DATA.format(cik=cik)
    computed={}
    annual_starts=set()
    preceding_intervals=[]
    for metric in metrics:
        annual=_facts(raw,metric,cutoff,ANNUAL_FORMS)
        matches=[r for r in annual if r["end"]==previous_end.isoformat()
                 and 330<=(_date(r["end"])-_date(r["start"])).days+1<=400]
        fy=_choose(matches,metric,"previous_fy")
        annual_starts.add(fy["start"])
        rows=_facts(raw,metric,cutoff,INTERIM_FORMS)
        matches=[r for r in rows if r["start"]==current_start.isoformat()
                 and r["end"]==current_end.isoformat()]
        current=_choose(matches,metric,"current_ytd")
        prior_matches=[r for r in rows if r["start"]==fy["start"]
                       and abs((_date(r["end"])-_date(r["start"])).days+1-current_span)<=7
                       and 357<=(current_end-_date(r["end"])).days<=378]
        if prior_matches:
            closest=min(abs((current_end-_date(r["end"])).days-364) for r in prior_matches)
            prior_matches=[r for r in prior_matches
                           if abs((current_end-_date(r["end"])).days-364)==closest]
        prior=_choose(prior_matches,metric,"prior_ytd")
        preceding_intervals.append((prior["start"],prior["end"]))
        components={"previous_fy":fy,"current_ytd":current,"prior_ytd":prior}
        for part in components.values():
            part["source_url"]=url
        computed[metric]={"value_usd":fy["value_usd"]+current["value_usd"]-prior["value_usd"],
                          "formula":"FY + CURRENT_YTD - PRIOR_YTD","components":components}
    if len(annual_starts)!=1 or len(set(preceding_intervals))!=1:
        raise ValueError("financial flows have different annual or comparable YTD periods")
    result={"version":VERSION,"cik":f"{cik:010d}","company":raw.get("entityName"),
            "as_of":as_of,"ttm_end":current_ytd_end,"previous_fy_end":previous_end.isoformat(),
            "ttm_start":(_date(preceding_intervals[0][1])+dt.timedelta(days=1)).isoformat(),
            "currency":"USD","metrics":computed,
            "restrictions":["Flow metrics only, not a balance-sheet snapshot",
                            "CFO minus capex is not unlevered FCFF",
                            "No earnings forecast, financial recommendation or automatic DCF"]}
    if "cfo" in computed and "capex" in computed:
        result["cfo_less_capex_usd"]=computed["cfo"]["value_usd"]-computed["capex"]["value_usd"]
        result["cfo_less_capex_is_fcff"]=False
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description="Offline SEC US-GAAP TTM financial statements")
    p.add_argument("--companyfacts",required=True)
    p.add_argument("--as-of",required=True)
    p.add_argument("--current-ytd-end",required=True)
    p.add_argument("--prior-fy-end")
    p.add_argument("--out",required=True)
    args=p.parse_args(argv)
    data=json.loads(Path(args.companyfacts).read_text(encoding="utf-8"))
    output=compute_ttm(data,as_of=args.as_of,current_ytd_end=args.current_ytd_end,
                       prior_fy_end=args.prior_fy_end)
    target=Path(args.out);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(output,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    print(f"CIK {output['cik']} | TTM {output['ttm_end']} | {target}")

if __name__=="__main__":
    main()
