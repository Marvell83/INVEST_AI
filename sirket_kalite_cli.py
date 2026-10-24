"""Offline quality report CLI: Piotroski F-Score plus separate issuer ratings."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from kredi_notlari import CreditRatingLedger, company_quality_snapshot

def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def main(argv=None):
    parser = argparse.ArgumentParser(description="INVEST_AI financial quality and issuer credit risk")
    commands = parser.add_subparsers(dest="command", required=True)
    report = commands.add_parser("report", help="SEC XBRL F-Score and optional rating snapshot")
    report.add_argument("--companyfacts", required=True)
    report.add_argument("--as-of", required=True)
    report.add_argument("--sector", required=True, choices=("non_financial", "financial", "unknown"))
    report.add_argument("--equity-evidence", help="Optional manually reviewed issuance evidence JSON")
    report.add_argument("--ratings-db", help="Optional rating history SQLite file")
    report.add_argument("--out", required=True)
    rating = commands.add_parser("rating-add", help="Append one source-cited rating event")
    rating.add_argument("--ratings-db", required=True)
    rating.add_argument("--event", required=True, help="JSON rating observation")
    args = parser.parse_args(argv)
    if args.command == "rating-add":
        with CreditRatingLedger(args.ratings_db) as ledger:
            ident = ledger.add(**_load(args.event))
        print("Stored manual rating event:", ident)
        return
    result = company_quality_snapshot(_load(args.companyfacts), as_of=args.as_of,
                                      sector=args.sector, equity_offering_evidence=(_load(args.equity_evidence)
                                                                                    if args.equity_evidence else None), credit_db=args.ratings_db)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False),
                   encoding="utf-8")
    p = result["piotroski"]
    print(result["cik"], "F-Score:", p["score"], "known:", p["known_count"],
          "possible range:", p["score_range"], "output:", out)

if __name__ == "__main__":
    main()
