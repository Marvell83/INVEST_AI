"""SEC nightly companyfacts.zip -> resumable SQLite financial screener.

No paid API, no price invention. Memory bounded per issuer; ZIP is read in-place
without extraction. Restarting the same archive resumes completed CIKs.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import urllib.error
import urllib.request
import zipfile

from finansal_tablolar import build_annual_statements
from finansal_oranlar import compute_ratios
from hisse_tarama_tablosu import COLUMNS, COLUMN_KEYS, _lineup
from sec_arsiv import (SECThrottle, atomic_write, canonical_bytes,
                       download_ticker_map, load_json, ticker_mapping)

BULK_URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
ZIP_REL = "veri/companyfacts.zip"
DB_REL = "veri/invest_ai_evren.sqlite3"
TICKER_REL = "veri/sec_ticker_esleme.json"
MAX_ZIP_BYTES = 3_000_000_000
MAX_MEMBER_BYTES = 70_000_000
MIN_FREE_DISK_BYTES = 4_500_000_000
BATCH_COMMIT = 25
ZIP_NAME = re.compile(r"(?:^|/)CIK(\d{10})\.json\Z", re.IGNORECASE)


def _utc():
    return datetime.now(timezone.utc).isoformat()


def fetch_bulk_zip(target, *, user_agent, progress=None, opener=urllib.request.urlopen):
    """Stream official bulk ZIP with Range resume if supported; never buffer whole ZIP."""
    if not re.search(r"\S+@\S+\.\S+", user_agent or ""):
        raise ValueError("SEC_USER_AGENT requires your actual contact email")
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        # Opening ZIP checks its central directory without decompressing 10+ GB.
        # Each relevant member is CRC-checked later by ZipFile.open().
        with zipfile.ZipFile(target) as archive:
            if not archive.infolist():
                raise ValueError("SEC bulk ZIP is empty")
        return target
    if shutil.disk_usage(target.parent).free < MIN_FREE_DISK_BYTES:
        raise OSError("SEC bulk ZIP requires at least 4.5 GB free disk before starting")
    temporary = target.with_name(target.name + ".part")
    offset = temporary.stat().st_size if temporary.is_file() else 0
    headers = {"User-Agent": user_agent, "Accept": "application/zip",
               "Accept-Encoding": "identity"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(BULK_URL, headers=headers)
    try:
        response = opener(request, timeout=90)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and offset:
            # Partial file might already be complete; validate before promotion.
            with zipfile.ZipFile(temporary) as archive:
                if archive.testzip() is not None:
                    raise ValueError("Partial bulk ZIP has a bad member CRC") from exc
            os.replace(temporary, target)
            return target
        raise
    with response:
        status = getattr(response, "status", 200)
        resume = bool(offset and status == 206)
        if resume:
            content_range = response.headers.get("Content-Range", "")
            if not content_range.startswith(f"bytes {offset}-"):
                raise ValueError("SEC range response does not match local partial ZIP")
        # Server can decline Range; restart the download rather than append corrupt bytes.
        mode = "ab" if resume else "wb"
        size = offset if resume else 0
        length = response.headers.get("Content-Length", "")
        if length and length.isdigit() and size + int(length) > MAX_ZIP_BYTES:
            raise ValueError("SEC bulk ZIP exceeds configured 3GB safety limit")
        if progress:
            progress({"phase": "downloading", "downloaded_bytes": size,
                      "message": "SEC toplu şirket finansalları indiriliyor"})
        with temporary.open(mode) as handle:
            while True:
                data = response.read(1024 * 1024)
                if not data:
                    break
                size += len(data)
                if size > MAX_ZIP_BYTES:
                    raise ValueError("SEC ZIP grew beyond 3GB safety limit")
                handle.write(data)
                if progress and size % (32 * 1024 * 1024) < len(data):
                    progress({"phase": "downloading", "downloaded_bytes": size})
    if not zipfile.is_zipfile(temporary):
        raise ValueError("Downloaded SEC file is not a valid ZIP; partial kept for diagnosis")
    # Zip CRC is verified per relevant member during ingestion, not by extracting everything.
    os.replace(temporary, target)
    return target


def _connect(db):
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS companies (
            cik TEXT PRIMARY KEY, ticker TEXT NOT NULL, company TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING', snapshot TEXT NOT NULL,
            payload TEXT, error TEXT
        );
        CREATE INDEX IF NOT EXISTS companies_ticker ON companies(ticker);
    """)
    return conn


def _placeholders(mapping):
    companies = {}
    for ticker, cik in sorted(mapping.items()):
        padded = f"{cik:010d}"
        companies.setdefault(padded, ticker)  # multiple tickers on one CIK share issuer facts
    return companies


def _empty_row(cik, ticker, name, as_of, status, reason):
    row = {key: None for key in COLUMN_KEYS}
    row.update(cik=cik, ticker=ticker, company=name or ticker, fiscal_year=None,
               as_of=as_of, source_mode="SEC_BULK_ZIP", sector="unknown",
               report_url=None, roic_warning=False, ebitda_approximate=False,
               price_source=None, price_date=None, screening_status=status,
               screening_reason=reason)
    return row


def ingest_zip(root, *, archive_path=None, as_of=None, max_companies=None,
               progress=None, retry_errors=False):
    """Checkpoint each 25 SEC issuers; optionally retry errors without deleting OK rows."""
    root = Path(root).resolve()
    zip_path = Path(archive_path).resolve() if archive_path else root / ZIP_REL
    ticker_path = root / TICKER_REL
    if not zip_path.is_file():
        raise FileNotFoundError("Missing SEC companyfacts.zip; download it first")
    if not ticker_path.is_file():
        raise FileNotFoundError("Missing SEC ticker directory; use SEC verilerini tara first")
    db = root / DB_REL
    old_snapshot = None
    if db.is_file():
        with closing(sqlite3.connect(db)) as existing:
            try:
                saved = existing.execute("SELECT key,value FROM metadata "
                                         "WHERE key IN ('snapshot','as_of')").fetchall()
                stored = dict(saved)
                old_snapshot = stored.get("snapshot")
                # Preserve the original as-of for repeatable continuation, even
                # when the operator resumes on another calendar date.
                if as_of is None:
                    as_of = stored.get("as_of")
            except sqlite3.OperationalError:
                pass
    if as_of is None:
        as_of = datetime.now(timezone.utc).date().isoformat()
    datetime.fromisoformat(as_of)
    if max_companies is not None and (type(max_companies) is not int or max_companies <= 0):
        raise ValueError("max_companies must be positive integer")
    mapping = ticker_mapping(load_json(ticker_path, max_bytes=12_000_000))
    issuers = _placeholders(mapping)
    names = {}
    raw_map = load_json(ticker_path, max_bytes=12_000_000)
    values = raw_map.values() if isinstance(raw_map, dict) else raw_map
    for item in values:
        names[item["ticker"].strip().upper()] = str(item.get("title", ""))[:300]
    signature = f"{zip_path.stat().st_size}|{zip_path.stat().st_mtime_ns}|{as_of}"
    if retry_errors and old_snapshot != signature:
        raise ValueError("Cannot retry errors across a different SEC ZIP/as-of snapshot")
    processed = 0
    failed = 0
    with zipfile.ZipFile(zip_path) as source, closing(_connect(db)) as conn:
        paths = {}
        for meta in source.infolist():
            match = ZIP_NAME.search(meta.filename)
            if match:
                paths[match.group(1)] = meta
        with conn:
            old = conn.execute("SELECT value FROM metadata WHERE key='snapshot'").fetchone()
            if not old or old[0] != signature:
                conn.execute("DELETE FROM companies")
                conn.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('snapshot',?)", (signature,))
                conn.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('as_of',?)", (as_of,))
            conn.executemany(
                "INSERT OR IGNORE INTO companies(cik,ticker,company,status,snapshot) VALUES(?,?,?,'PENDING',?)",
                ((cik, ticker, names.get(ticker, ""), signature) for cik,ticker in issuers.items()))
        pending = conn.execute(
            "SELECT cik,ticker,company FROM companies WHERE status=? ORDER BY cik" +
            (" LIMIT ?" if max_companies else ""),
            (("ERROR" if retry_errors else "PENDING"), max_companies)
            if max_companies else (("ERROR" if retry_errors else "PENDING"),)
        ).fetchall()
        total = len(issuers)
        existing = total - conn.execute(
            "SELECT count(*) FROM companies WHERE status='PENDING'").fetchone()[0]
        retries_attempted = 0
        if progress:
            progress({"phase":"processing","processed":existing,"total":total,
                      "message":"SEC finansal dosyaları şirket bazında işleniyor"})
        for cik, ticker, name in pending:
            try:
                member = paths.get(cik)
                if member is None:
                    status, why = "NO_COMPANYFACTS", "SEC_BULK_NO_MATCHING_CIK"
                    row = _empty_row(cik, ticker, name, as_of, status, why)
                elif member.file_size > MAX_MEMBER_BYTES:
                    status, why = "TOO_LARGE", "JSON_OVER_70MB_LIMIT"
                    row = _empty_row(cik, ticker, name, as_of, status, why)
                else:
                    with source.open(member) as handle:
                        data = handle.read(MAX_MEMBER_BYTES + 1)
                    if len(data) > MAX_MEMBER_BYTES:
                        raise ValueError("Individual SEC JSON is too large")
                    raw = json.loads(data)
                    if f"{int(raw.get('cik', -1)):010d}" != cik:
                        raise ValueError("CIK mismatch between ZIP path and JSON")
                    if not isinstance(raw.get("facts"), dict):
                        raise ValueError("SEC file lacks facts object")
                    # Missing annual 10-K US-GAAP years are coverage gaps, not
                    # computation exceptions. _lineup intentionally returns None
                    # when no fiscal years exist; never classify that as ERROR.
                    statements = build_annual_statements(raw, as_of=as_of, years=5, ebit_proxy=False)
                    if not statements["years"]:
                        status = "NO_SUPPORTED_ANNUAL_DATA"
                        namespaces = sorted(str(k) for k in raw["facts"])
                        why = ("NO_US_GAAP_NAMESPACE" if not raw["facts"].get("us-gaap")
                               else "NO_ELIGIBLE_US_GAAP_10K_FISCAL_YEAR")
                        row = _empty_row(cik, ticker, raw.get("entityName") or name,
                                         as_of, status, why)
                        row["screening_detail"] = (
                            "Available fact namespaces: " +
                            (", ".join(namespaces[:8]) if namespaces else "none"))
                    else:
                        ratios = compute_ratios(statements)
                        report = {"cik":cik, "company":raw.get("entityName") or name,
                                  "as_of":as_of,"sector_assumption":"unknown",
                                  "source":{"mode":"SEC_BULK_ZIP"},
                                  "financial_statements":statements,
                                  "financial_ratios":ratios}
                        row = _lineup(report,ticker=ticker,path=None)
                        if row is None:
                            raise ValueError("Financial ratio row missing despite eligible annual years")
                        status, why = "OK", ""
                        row.update(screening_status=status, screening_reason=why)
            except (ValueError, TypeError, KeyError, UnicodeError, OverflowError,
                    zipfile.BadZipFile, OSError, MemoryError) as exc:
                # Distinguish thousands of malformed issuer facts by actual cause.
                # Keep only bounded safe diagnostics, never raw SEC JSON.
                detail = " ".join(str(exc).split())[:220]
                status, why = "ERROR", type(exc).__name__
                error_text = why + (": " + detail if detail else "")
                row = _empty_row(cik, ticker, name, as_of, status, why)
                row["screening_detail"] = error_text
                failed += 1
            else:
                error_text = why
            if retry_errors:
                retries_attempted += 1
            conn.execute("UPDATE companies SET status=?,payload=?,error=? WHERE cik=?",
                         (status, json.dumps(row, ensure_ascii=False, allow_nan=False),
                          error_text, cik))
            processed += 1
            if processed % BATCH_COMMIT == 0:
                conn.commit()
                if progress:
                    progress({"phase":"processing","processed":existing+processed,
                              "total":total,"errors":failed})
        conn.commit()
        tally = dict(conn.execute("SELECT status,count(*) FROM companies GROUP BY status").fetchall())
        error_types = dict(conn.execute(
            "SELECT CASE WHEN instr(error, ':')>0 THEN substr(error,1,instr(error,':')-1) "
            "ELSE error END, count(*) FROM companies "
            "WHERE status='ERROR' GROUP BY 1 ORDER BY count(*) DESC").fetchall())
    result = {"phase":"complete" if "PENDING" not in tally else "partial",
              "processed":total-tally.get("PENDING",0), "total":total,
              "statuses":tally, "errors":tally.get("ERROR",0),
              "error_types":error_types, "retries_attempted":retries_attempted,
              "database":DB_REL, "as_of":as_of, "finished_utc":_utc()}
    if progress:
        progress(result)
    return result


def diagnose_database(root, *, sample_limit=12):
    """Read-only status/error distribution without reprocessing a single SEC issuer."""
    db = Path(root).resolve() / DB_REL
    if not db.is_file():
        raise FileNotFoundError("No local SEC screener database found")
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as conn:
        tally = dict(conn.execute("SELECT status,count(*) FROM companies GROUP BY status").fetchall())
        errors = conn.execute(
            "SELECT error,count(*) AS n FROM companies WHERE status='ERROR' "
            "GROUP BY error ORDER BY n DESC LIMIT 20").fetchall()
        samples = conn.execute(
            "SELECT cik,ticker,error FROM companies WHERE status='ERROR' "
            "ORDER BY cik LIMIT ?", (sample_limit,)).fetchall()
        meta = dict(conn.execute("SELECT key,value FROM metadata").fetchall())
    return {"status_counts":tally, "error_reasons":[{"error": e, "count": n} for e,n in errors],
            "error_examples":[{"cik": cik,"ticker":ticker,"error":error}
                              for cik,ticker,error in samples],
            "snapshot_as_of":meta.get("as_of"),"snapshot":meta.get("snapshot")}


def load_bulk_grid(root):
    """Read a large saved SEC universe without loading raw SEC JSONs again."""
    path = Path(root).resolve() / DB_REL
    if not path.is_file():
        return None
    from hisse_tarama_tablosu import VERSION
    con = sqlite3.connect(path.as_uri()+"?mode=ro", uri=True)
    try:
        rows = [json.loads(item[0]) if item[0] else
                _empty_row(item[1], item[2], item[3], None, item[4], "NOT_PROCESSED")
                for item in con.execute("SELECT payload,cik,ticker,company,status FROM companies ORDER BY ticker")]
        tally = dict(con.execute("SELECT status,count(*) FROM companies GROUP BY status"))
    finally:
        con.close()
    issuer_count = len(rows)
    # A financial issuer may have several public share classes (GOOG/GOOGL, etc).
    # Preserve all SEC ticker symbols without re-parsing the underlying CIK facts.
    ticker_path = Path(root).resolve() / TICKER_REL
    if ticker_path.is_file():
        by_cik = {item["cik"]: item for item in rows}
        map_data = ticker_mapping(load_json(ticker_path, max_bytes=12_000_000))
        expanded = []
        for ticker, number in sorted(map_data.items()):
            cik = f"{number:010d}"
            if cik not in by_cik:
                continue
            expanded.append({**by_cik[cik], "ticker":ticker})
        rows = expanded
    return {"version":VERSION,"columns":COLUMNS,"rows":rows,"available":len(rows),
            "issuer_count":issuer_count, "scope":"BULK_SEC_COMPANYFACTS", "screening_counts":tally,
            "market_price_fetched":False,
            "notes":["Company Facts only, price/PEG unprovided; missing is never zero",
                     "SEC ticker list is not a validated listed-common-stock-only universe",
                     "Issuer XBRL taxonomy/form gaps remain unknown or blank",
                     "Ticker share classes listed separately; CIK-level financials are shared between classes"]}


def run(root, *, zip_path=None, limit=None, progress=None, user_agent=None,
        retry_errors=False):
    root = Path(root).resolve()
    archive = Path(zip_path).resolve() if zip_path else root / ZIP_REL
    mapping = root / TICKER_REL
    if not mapping.is_file():
        if not user_agent:
            raise ValueError("SEC_USER_AGENT needed to download ticker map")
        source = download_ticker_map(user_agent=user_agent, limiter=SECThrottle(interval=1.0))
        atomic_write(mapping, canonical_bytes(source))
    if not archive.is_file():
        fetch_bulk_zip(archive, user_agent=user_agent, progress=progress)
    return ingest_zip(root, archive_path=archive, max_companies=limit, progress=progress,
                      retry_errors=retry_errors)


def main(argv=None):
    parser = argparse.ArgumentParser(description="SEC bulk nightly companyfacts zip -> local full-market screener")
    parser.add_argument("--root", default=".", help="INVEST_AI checkout root")
    parser.add_argument("--zip", help="Use an existing downloaded companyfacts.zip")
    parser.add_argument("--limit", type=int, help="Process at most N companies per invocation")
    parser.add_argument("--diagnose", action="store_true", help="Print status and errors without processing")
    parser.add_argument("--retry-errors", action="store_true",
                        help="Reprocess ERROR rows only; preserve successful analyses")
    args = parser.parse_args(argv)
    if args.diagnose:
        print(json.dumps(diagnose_database(args.root),ensure_ascii=False,indent=2))
        return 0
    def status(info):
        print(json.dumps(info,ensure_ascii=False),flush=True)
    run(args.root, zip_path=args.zip, limit=args.limit, retry_errors=args.retry_errors,
        user_agent=os.getenv("SEC_USER_AGENT",""), progress=status)


if __name__ == "__main__":
    main()
