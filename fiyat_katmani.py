"""INVEST_AI — dated, source-cited share prices for the full-market screener.

SEC Company Facts has no market prices. This layer imports a price file the
analyst obtained legally (for example the free "Download CSV" of the Nasdaq
stock screener, or any CSV with symbol / date / close columns) into a local
SQLite table. Every price keeps its date and source; nothing is fetched,
estimated or carried forward here.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import csv
from datetime import date, datetime, timezone
import io
import json
import math
from pathlib import Path
import re
import sqlite3

DB_REL = "veri/invest_ai_fiyat.sqlite3"
MAX_CSV_BYTES = 60_000_000
MAX_ROWS = 300_000
MAX_PRICE = 10_000_000
SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9-]{0,14}")
# Accepted header names (lower case) for each field; Nasdaq screener names first.
HEADERS = {
    "symbol": ("symbol", "ticker", "sembol", "hisse", "kod"),
    "price": ("last sale", "close", "adj close", "price", "last", "fiyat", "kapanış", "kapanis"),
    "date": ("date", "tarih", "price date", "fiyat tarihi"),
    "market_cap": ("market cap", "piyasa değeri", "piyasa degeri"),
    "sector": ("sector", "sektör", "sektor"),
    "industry": ("industry", "endüstri", "endustri"),
}


def normalize_ticker(symbol):
    """SEC style ticker (BRK/B, BRK.B -> BRK-B); None for preferred shares, units or junk."""
    text = str(symbol or "").strip().upper().replace("/", "-").replace(".", "-")
    return text if SYMBOL.fullmatch(text) else None


def _number(text, decimal_comma=False):
    """'$1,234.5' -> 1234.5; with decimal_comma (Turkish / European CSV) '1.234,5' -> 1234.5."""
    cleaned = str(text or "").strip().replace("$", "").replace(" ", "")
    if decimal_comma:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _iso_date(text, field):
    try:
        return date.fromisoformat(str(text).strip()).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field}: ISO YYYY-MM-DD date required") from exc


def _columns(header):
    lookup = {name.strip().lower(): index for index, name in enumerate(header)}
    found = {}
    for field, names in HEADERS.items():
        found[field] = next((lookup[n] for n in names if n in lookup), None)
    if found["symbol"] is None or found["price"] is None:
        raise ValueError("CSV needs a symbol/ticker column and a price column (e.g. 'Last Sale' or 'Close')")
    return found


def read_price_csv(path, *, price_date=None, today=None):
    """Parse a price CSV into rows; invalid lines are counted by reason, never guessed."""
    path = Path(path)
    if path.stat().st_size > MAX_CSV_BYTES:
        raise ValueError("price CSV is larger than the 60 MB safety limit")
    text = path.read_text(encoding="utf-8-sig")
    sample = text[:4096]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    # A semicolon-separated file is the Turkish / European Excel export: decimal comma.
    decimal_comma = delimiter == ";"
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = next(reader, None)
    if not header:
        raise ValueError("price CSV is empty")
    cols = _columns(header)
    if cols["date"] is None and price_date is None:
        raise ValueError("this CSV has no date column: give the trading date of its prices (--date)")
    today = today or datetime.now(timezone.utc).date()
    default_date = _iso_date(price_date, "price_date") if price_date is not None else None
    if default_date and date.fromisoformat(default_date) > today:
        raise ValueError("price_date is in the future")
    rows, skipped = {}, {}

    def skip(reason):
        skipped[reason] = skipped.get(reason, 0) + 1

    def cell(line, field):
        index = cols[field]
        return line[index] if index is not None and index < len(line) else ""
    for number, line in enumerate(reader):
        if number >= MAX_ROWS:
            raise ValueError("price CSV has more than 300,000 rows")
        if not any(part.strip() for part in line):
            continue
        ticker = normalize_ticker(cell(line, "symbol"))
        if ticker is None:
            skip("UNSUPPORTED_SYMBOL")
            continue
        price = _number(cell(line, "price"), decimal_comma)
        if price is None or not 0 < price < MAX_PRICE:
            skip("INVALID_PRICE")
            continue
        try:
            day = _iso_date(cell(line, "date"), "date") if cols["date"] is not None and cell(line, "date") \
                else default_date
        except ValueError:
            skip("INVALID_DATE")
            continue
        if day is None:
            skip("MISSING_DATE")
            continue
        if date.fromisoformat(day) > today:
            skip("FUTURE_DATE")
            continue
        if (ticker, day) in rows:
            skip("DUPLICATE_SYMBOL_DATE")
            continue
        cap = _number(cell(line, "market_cap"), decimal_comma)
        rows[(ticker, day)] = {
            "ticker": ticker, "price_date": day, "price": price,
            "market_cap": cap if cap is not None and cap > 0 else None,
            "sector": cell(line, "sector").strip()[:80] or None,
            "industry": cell(line, "industry").strip()[:160] or None,
        }
    return list(rows.values()), skipped


def _connect(db):
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS prices (
            ticker TEXT NOT NULL, price_date TEXT NOT NULL, price REAL NOT NULL,
            source TEXT NOT NULL, market_cap REAL, sector TEXT, industry TEXT,
            imported_utc TEXT NOT NULL, PRIMARY KEY (ticker, price_date)
        );
    """)
    return conn


def import_prices(root, csv_path, *, source, price_date=None, today=None):
    """Store one price file; a later import of the same ticker and date replaces it."""
    if not isinstance(source, str) or len(source.strip()) < 8:
        raise ValueError("source: a citation of at least 8 characters is required")
    rows, skipped = read_price_csv(csv_path, price_date=price_date, today=today)
    if not rows:
        raise ValueError("no usable price rows in the CSV")
    stamp = datetime.now(timezone.utc).isoformat()
    with closing(_connect(Path(root).resolve() / DB_REL)) as conn, conn:
        conn.executemany(
            "INSERT OR REPLACE INTO prices(ticker,price_date,price,source,market_cap,sector,industry,imported_utc) "
            "VALUES(:ticker,:price_date,:price,:source,:market_cap,:sector,:industry,:imported_utc)",
            [dict(r, source=source.strip(), imported_utc=stamp) for r in rows])
    dates = sorted({r["price_date"] for r in rows})
    return {"imported": len(rows), "skipped": skipped, "dates": [dates[0], dates[-1]],
            "source": source.strip(), "database": DB_REL}


def price_history(root):
    """{ticker: [price records, newest first]}; empty when no price was imported."""
    db = Path(root).resolve() / DB_REL
    if not db.is_file():
        return {}
    history = {}
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        for record in conn.execute("SELECT * FROM prices ORDER BY ticker, price_date DESC"):
            history.setdefault(record["ticker"], []).append(dict(record))
    return history


def pick_price(records, data_date, window_days):
    """Newest price within `window_days` of the SEC data date, else the newest price (shown, not used)."""
    if not records:
        return None
    try:
        anchor = date.fromisoformat(data_date)
    except (TypeError, ValueError):
        return records[0]
    near = [r for r in records if abs((date.fromisoformat(r["price_date"]) - anchor).days) <= window_days]
    return near[0] if near else records[0]


def price_summary(root):
    db = Path(root).resolve() / DB_REL
    if not db.is_file():
        return {"tickers": 0, "imports": []}
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as conn:
        imports = conn.execute("SELECT price_date, source, count(*) FROM prices GROUP BY price_date, source "
                               "ORDER BY price_date DESC").fetchall()
        tickers = conn.execute("SELECT count(DISTINCT ticker) FROM prices").fetchone()[0]
    return {"tickers": tickers,
            "imports": [{"price_date": d, "source": s, "rows": n} for d, s, n in imports]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Import a dated, source-cited share price CSV for the screener")
    parser.add_argument("--root", default=".", help="INVEST_AI checkout root")
    parser.add_argument("--csv", help="price CSV (Nasdaq screener download or symbol/date/close)")
    parser.add_argument("--date", help="trading date of the prices when the CSV has no date column")
    parser.add_argument("--source", help="where the prices come from, e.g. 'Nasdaq stock screener CSV, 2026-10-24'")
    parser.add_argument("--summary", action="store_true", help="show imported price dates and sources")
    args = parser.parse_args(argv)
    if args.summary or not args.csv:
        print(json.dumps(price_summary(args.root), ensure_ascii=False, indent=2))
        return 0
    if not args.source:
        parser.error("--source is required with --csv")
    result = import_prices(args.root, args.csv, source=args.source, price_date=args.date)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    main()
