"""Offline command-line entry point for audited SEC -> DCF -> SQLite records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sec_reviewed_pipeline import analyze_and_record


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audited SEC Company Facts to v0.2 forecast ledger")
    parser.add_argument("--companyfacts", required=True, help="raw SEC Company Facts .json file")
    parser.add_argument("--as-of", required=True, help="YYYY-MM-DD knowledge cutoff")
    parser.add_argument("--proposal", required=True, help="JSON containing manually sourced assumptions")
    parser.add_argument("--fy-ends", required=True, help="JSON array of forecast fiscal period ends")
    parser.add_argument("--db", required=True, help="SQLite forecast ledger file")
    parser.add_argument("--out", required=True, help="JSON result path")
    opts = parser.parse_args(argv)
    def load_json(path):
        with open(path, encoding="utf-8") as reader:
            return json.load(reader)
    result = analyze_and_record(raw_companyfacts=load_json(opts.companyfacts),
                                as_of=opts.as_of, proposal=load_json(opts.proposal),
                                future_period_ends=load_json(opts.fy_ends), db_path=opts.db)
    output = Path(opts.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print("Recorded", result["forecast_rows"], "forecast rows for CIK", result["cik"])
    print("Experimental model, not investment advice. Result:", output)


if __name__ == "__main__":
    main()
