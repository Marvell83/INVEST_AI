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
from fiyat_katmani import pick_price, price_history
from hisse_tarama_tablosu import (COLUMNS, COLUMN_KEYS, PRICE_WINDOW_DAYS, ROW_SCHEMA, STALE_FINANCIALS_DAYS,
                                  _lineup, apply_market_price, financials_age_days)
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


class SourceCIKMismatch(Exception):
    """Source ZIP path refers to a different issuer than its JSON payload."""

    def __init__(self, expected, reported):
        super().__init__(f"ZIP CIK {expected}; JSON CIK {reported}")
        self.expected = expected
        self.reported = reported


def _utc():
    return datetime.now(timezone.utc).isoformat()


def fetch_bulk_zip(target, *, user_agent, progress=None, opener=urllib.request.urlopen, url=BULK_URL):
    """Stream an official SEC bulk ZIP with Range resume if supported; never buffer whole ZIP."""
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
    request = urllib.request.Request(url, headers=headers)
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
               screening_reason=reason, row_schema=ROW_SCHEMA)
    return row


def ingest_zip(root, *, archive_path=None, as_of=None, max_companies=None,
               progress=None, retry_errors=False, rebuild=False):
    """Checkpoint each 25 SEC issuers; optionally retry errors without deleting OK rows.

    `rebuild` recomputes every issuer of the same local ZIP and as-of date (for
    new screener columns) without downloading anything; an interrupted rebuild
    continues on the next run, and old rows stay visible until replaced.
    """
    if rebuild and retry_errors:
        raise ValueError("rebuild already reprocesses every issuer; do not combine with retry_errors")
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
    if (retry_errors or rebuild) and old_snapshot != signature:
        raise ValueError("Cannot retry or rebuild across a different SEC ZIP/as-of snapshot")
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
            elif rebuild:
                conn.execute("UPDATE companies SET status='PENDING'")
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
        retries_attempted = 0
        retry_total = len(pending) if retry_errors else 0
        completed = total - conn.execute(
            "SELECT count(*) FROM companies WHERE status='PENDING'").fetchone()[0]
        if progress:
            progress({"phase":"processing","processed":completed,"total":total,
                      "retry_attempted":0,"retry_total":retry_total,
                      "message":("Hatalı SEC kayıtları yeniden değerlendiriliyor"
                                 if retry_errors else "SEC finansal dosyaları şirket bazında işleniyor")})
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
                    try:
                        json_cik = f"{int(raw.get('cik')):010d}"
                    except (TypeError, ValueError) as exc:
                        raise ValueError("SEC JSON CIK is missing or not numeric") from exc
                    if json_cik != cik:
                        raise SourceCIKMismatch(cik, json_cik)
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
            except SourceCIKMismatch as exc:
                # Keep source identity mismatches out of financial quality
                # screens. Never attribute another CIK's facts to this ticker.
                status, why = "SOURCE_CIK_MISMATCH", "ZIP_JSON_CIK_MISMATCH"
                error_text = f"{why}: expected={exc.expected}; reported={exc.reported}"
                row = _empty_row(cik, ticker, name, as_of, status, why)
                row["screening_detail"] = error_text
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
                    completed = total - conn.execute(
                        "SELECT count(*) FROM companies WHERE status='PENDING'").fetchone()[0]
                    progress({"phase":"processing","processed":completed,
                              "total":total,"errors":failed,
                              "retry_attempted":retries_attempted,
                              "retry_total":retry_total})
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
              "retry_total":retry_total,
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
        identity_mismatches = conn.execute(
            "SELECT cik,ticker,error FROM companies WHERE status='SOURCE_CIK_MISMATCH' "
            "ORDER BY cik LIMIT ?", (sample_limit,)).fetchall()
        meta = dict(conn.execute("SELECT key,value FROM metadata").fetchall())
    return {"status_counts":tally, "error_reasons":[{"error": e, "count": n} for e,n in errors],
            "error_examples":[{"cik": cik,"ticker":ticker,"error":error}
                              for cik,ticker,error in samples],
            "identity_mismatches":[{"cik":cik,"ticker":ticker,"detail":error}
                                   for cik,ticker,error in identity_mismatches],
            "snapshot_as_of":meta.get("as_of"),"snapshot":meta.get("snapshot")}


def _attach_prices(root, rows):
    """Attach the imported price nearest the SEC data date to each row; returns status counts."""
    history = price_history(root)
    counts = {}
    for row in rows:
        record = pick_price(history.get(row.get("ticker")), row.get("as_of"), PRICE_WINDOW_DAYS)
        if record is None:
            row["valuation_status"] = "NO_PRICE"
        else:
            apply_market_price(row, record)
        counts[row["valuation_status"]] = counts.get(row["valuation_status"], 0) + 1
    return counts


def _ok_rows(conn):
    return [json.loads(payload) for (payload,) in conn.execute(
        "SELECT payload FROM companies WHERE status='OK' AND payload IS NOT NULL")]


# Inputs of the seven-condition pre-screen; ROIC counts only without a caution flag.
SCREEN_INPUTS = (("roe", "ROE"), ("roic", "ROIC (uyarısız)"), ("roe_10_pb", "(ROE / 10) / PD/DD"),
                 ("peg", "PEG"), ("net_debt_to_ebitda", "Net borç / FAVÖK*"),
                 ("cash_conversion_3y", "CFO / net kâr (3Y)"), ("fcf_3y", "3 yıllık toplam FCF"))
SEC_ONLY_INPUTS = ("roe", "roic", "net_debt_to_ebitda", "cash_conversion_3y", "fcf_3y")


def _usable(row, key):
    value = row.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    return not (key == "roic" and row.get("roic_warning"))


def coverage_report(root):
    """Read-only: how many OK issuers have each screener value, without reprocessing SEC files."""
    db = Path(root).resolve() / DB_REL
    if not db.is_file():
        raise FileNotFoundError("No local SEC screener database found")
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as conn:
        tally = dict(conn.execute("SELECT status,count(*) FROM companies GROUP BY status").fetchall())
        rows = _ok_rows(conn)
        meta = dict(conn.execute("SELECT key,value FROM metadata").fetchall())
    total = len(rows)
    # Price multiples count per issuer, with the price of the issuer's primary ticker.
    valuation = _attach_prices(root, rows)

    def share(count):
        return round(count / total, 4) if total else 0.0
    columns = []
    for key, label, unit, group in COLUMNS:
        if unit == "text":
            continue
        count = sum(_usable(r, key) for r in rows)
        columns.append({"key": key, "label": label, "group": group, "available": count, "share": share(count)})
    ages = [r.get("financials_age_days", financials_age_days(r.get("as_of"), r.get("fiscal_year")))
            for r in rows]
    stale = sum(age is not None and age > STALE_FINANCIALS_DAYS for age in ages)
    screen = [{"key": key, "label": label, "available": sum(_usable(r, key) for r in rows)}
              for key, label in SCREEN_INPUTS]
    for item in screen:
        item["share"] = share(item["available"])
    return {
        "snapshot_as_of": meta.get("as_of"), "status_counts": tally, "ok_issuers": total,
        "columns": columns, "screen_inputs": screen,
        "all_sec_only_inputs": sum(all(_usable(r, k) for k in SEC_ONLY_INPUTS) for r in rows),
        "roic_with_caution": sum(r.get("roic") is not None and bool(r.get("roic_warning")) for r in rows),
        "stale_financials": stale, "stale_threshold_days": STALE_FINANCIALS_DAYS,
        "rows_needing_rebuild": sum(r.get("row_schema", 1) < ROW_SCHEMA for r in rows),
        "valuation_counts": dict(sorted(valuation.items())),
    }


VALUATION_LABELS = {
    "OK": "uyumlu fiyat", "NO_PRICE": "fiyat yok", "STALE_FINANCIALS": "finansallar güncel değil",
    "PRICE_DATE_OUTSIDE_WINDOW": "fiyat tarihi SEC tarihinden uzak", "NO_SHARE_COUNT": "pay adedi yok",
    "SHARE_COUNT_DATE_NOT_ALIGNED": "pay adedi tarihi uyumsuz", "ROW_NEEDS_REBUILD": "satır eski (--rebuild)",
}


def coverage_lines(report):
    """Turkish reading of coverage_report, printed by --coverage."""
    total = report["ok_issuers"]
    lines = [f"Finansalları işlenmiş şirket (OK): {total} · SEC bilgi tarihi {report['snapshot_as_of']}"]
    if report["rows_needing_rebuild"]:
        lines.append(f"! {report['rows_needing_rebuild']} satır eski sürümle hesaplanmış; yeni sütunlar için "
                     "bir kez `--rebuild` çalıştır (indirme yapmaz).")
    lines.append(f"Son mali yılı {report['stale_threshold_days']} günden eski (güncel olmayan): "
                 f"{report['stale_financials']}")
    lines.append(f"ROIC var ama uyarılı (küçük sermaye veya yaklaşık EBIT): {report['roic_with_caution']}")
    lines.append("Fiyat ve değerleme: " + ", ".join(
        f"{VALUATION_LABELS.get(k, k)} {v}" for k, v in report["valuation_counts"].items()))
    lines.append("7 koşulun girdileri:")
    for item in report["screen_inputs"]:
        lines.append(f"  {item['label']:<24} {item['available']:>6}  %{item['share'] * 100:5.1f}")
    lines.append(f"Fiyat gerektirmeyen 5 girdinin hepsi dolu: {report['all_sec_only_inputs']}")
    lines.append("Bütün sayısal sütunlar (dolu şirket sayısı):")
    for item in report["columns"]:
        lines.append(f"  {item['label']:<44} {item['available']:>6}  %{item['share'] * 100:5.1f}")
    return lines


def load_bulk_grid(root):
    """Read a large saved SEC universe without loading raw SEC JSONs again."""
    path = Path(root).resolve() / DB_REL
    if not path.is_file():
        return None
    from hisse_tarama_tablosu import VERSION
    con = sqlite3.connect(path.as_uri()+"?mode=ro", uri=True)
    try:
        # Rows saved by an older screener version lack newer columns: show them as missing.
        blank = dict.fromkeys(COLUMN_KEYS)
        rows = [{**blank, **json.loads(item[0])} if item[0] else
                _empty_row(item[1], item[2], item[3], None, item[4], "NOT_PROCESSED")
                for item in con.execute("SELECT payload,cik,ticker,company,status FROM companies ORDER BY ticker")]
        for row in rows:
            if row.get("financials_age_days") is None:
                row["financials_age_days"] = financials_age_days(row.get("as_of"), row.get("fiscal_year"))
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
    # Each share class gets its own imported price; SEC financials stay shared per CIK.
    valuation = _attach_prices(root, rows)
    return {"version":VERSION,"columns":COLUMNS,"rows":rows,"available":len(rows),
            "issuer_count":issuer_count, "scope":"BULK_SEC_COMPANYFACTS", "screening_counts":tally,
            "market_price_fetched":False, "priced_rows": len(rows) - valuation.get("NO_PRICE", 0),
            "valuation_counts": dict(sorted(valuation.items())),
            "notes":["Company Facts only; prices only from a dated, source-cited local import; "
                     "forward PEG unprovided; missing is never zero",
                     "SEC ticker list is not a validated listed-common-stock-only universe",
                     "Issuer XBRL taxonomy/form gaps remain unknown or blank",
                     "Ticker share classes listed separately; CIK-level financials are shared between classes"]}


def run(root, *, zip_path=None, limit=None, progress=None, user_agent=None,
        retry_errors=False, rebuild=False):
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
                      retry_errors=retry_errors, rebuild=rebuild)


def main(argv=None):
    parser = argparse.ArgumentParser(description="SEC bulk nightly companyfacts zip -> local full-market screener")
    parser.add_argument("--root", default=".", help="INVEST_AI checkout root")
    parser.add_argument("--zip", help="Use an existing downloaded companyfacts.zip")
    parser.add_argument("--limit", type=int, help="Process at most N companies per invocation")
    parser.add_argument("--diagnose", action="store_true", help="Print status and errors without processing")
    parser.add_argument("--retry-errors", action="store_true",
                        help="Reprocess ERROR rows only; preserve successful analyses")
    parser.add_argument("--coverage", action="store_true",
                        help="Print how many processed issuers have each ratio (read-only)")
    parser.add_argument("--rebuild", action="store_true",
                        help="Recompute every issuer from the same local ZIP (new columns); no download")
    args = parser.parse_args(argv)
    if args.diagnose:
        print(json.dumps(diagnose_database(args.root),ensure_ascii=False,indent=2))
        return 0
    if args.coverage:
        print("\n".join(coverage_lines(coverage_report(args.root))))
        return 0
    def status(info):
        print(json.dumps(info,ensure_ascii=False),flush=True)
    run(args.root, zip_path=args.zip, limit=args.limit, retry_errors=args.retry_errors,
        rebuild=args.rebuild, user_agent=os.getenv("SEC_USER_AGENT",""), progress=status)


if __name__ == "__main__":
    main()
