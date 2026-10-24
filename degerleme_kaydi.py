"""Connect the frozen 0.1 DCF engine to the append-only forecast ledger.

Records annual revenue and FCFF forecasts only after a successful valuation.
Input sources and model assumptions are stored for reproducibility. This is
not a financial-data importer, and it does not validate economic assumptions.
"""
from __future__ import annotations

import math

from dogrulama.uretim_motoru import degerle
from degerleme_v02 import degerle_v02
from tahmin_defteri import TahminDefteri

def degerle_ve_kaydet(*, db_path, company, currency, base_year,
                       inputs, sources, scenario="base", engine="v0.1"):
    """Value once, persist a dated snapshot and annual forecast observations.

    Returns valuation and IDs. Uses an explicit transaction so failures
    cannot leave a partial valuation batch in the database.
    """
    if not isinstance(base_year, int) or isinstance(base_year, bool) or not 1900 <= base_year <= 2200:
        raise ValueError("base_year must be an integer calendar year")
    if not isinstance(company, str) or not company.strip():
        raise ValueError("company is required")
    if not isinstance(currency, str) or not currency.strip():
        raise ValueError("currency is required")
    if not isinstance(scenario, str) or not scenario.strip():
        raise ValueError("scenario is required")
    if not isinstance(sources, list) or not sources or not all(isinstance(s, str) and s.strip() for s in sources):
        raise ValueError("at least one source is required")
    if engine == "v0.1":
        result = degerle(inputs)
    elif engine == "v0.2":
        result = degerle_v02(inputs)
    else:
        raise ValueError("unknown valuation engine")
    if result["durum"] != "gecerli":
        return {"durum": "gecersiz", "degerleme": result, "tahmin_kimlikleri": []}
    rows = result["tablo"]
    if len(rows) != inputs["yillar"]:
        raise ValueError("inconsistent valuation horizon")
    for row in rows:
        if any(not math.isfinite(row[key]) for key in ("gelir", "fcff")):
            raise ValueError("non-finite forecast")
    # SQLite transaction: all six/ten/twenty records or none.
    with TahminDefteri(db_path) as ledger:
        ledger.db.execute("BEGIN IMMEDIATE")
        ids = []
        try:
            for row in rows:
                period = str(base_year + row["yil"]) + "-FY"
                for metric, key in (("revenue", "gelir"), ("fcff", "fcff")):
                    assumptions = {"inputs": inputs, "scenario": scenario,
                                   "base_year": base_year, "valuation_metric": metric,
                                   "valuation_result": {
                                       "firma_degeri": result["firma_degeri"],
                                       "ozsermaye_degeri": result["ozsermaye_degeri"],
                                       "hisse_basi_deger": result["hisse_basi_deger"],
                                       "uc_deger_payi": result["uc_deger_payi"]}}
                    if engine != "v0.1":
                        assumptions["engine"] = engine
                    fid = ledger.tahmin_kaydet(
                        company=company, metric=metric, target_period=period,
                        currency=currency, predicted=row[key],
                        model_version=result["motor_surumu"],
                        assumptions=assumptions, sources=sources)
                    ids.append(fid)
            ledger.db.commit()
        except Exception:
            ledger.db.rollback()
            raise
    return {"durum": "gecerli", "degerleme": result, "tahmin_kimlikleri": ids}
