"""INVEST_AI — evidence-preserving SEC Company Facts multi-issuer ingestion.

Standard library only. CIK identity is mandatory, optional ticker maps use
the official SEC company_tickers.json *snapshot*, not ticker-name guesses.
Immutable content-hash snapshots; a mutable index identifies the last capture.
Rate limiter is per PROCESS, not global to an IP or multiple machines.
No live prices, DCF, rankings, ETF look-through or automatic trade signals.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
import urllib.error
import urllib.request

from sec_companyfacts import SEC_DATA, _validate_cik, download_companyfacts
from sirket_arastirma_akisi import build_company_research, render_company_research

VERSION = "invest-ai-sec-batch-0.1.0"
TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")
SECTORS = frozenset(("non_financial", "financial", "unknown"))
HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
MAX_JSON = 50_000_000
MAX_TICKERS_JSON = 12_000_000


class StopSECRequests(Exception):
    """An access-control response stops ALL remaining external SEC requests."""


def _utc():
    return dt.datetime.now(dt.timezone.utc)


def _iso_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("as_of must be YYYY-MM-DD")
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("invalid as_of calendar date") from exc
    return value


def _int(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in {minimum}..{maximum}")
    return value


def _check_doc(raw, cik):
    if not isinstance(raw, dict) or not isinstance(raw.get("facts"), dict):
        raise ValueError("raw SEC Company Facts JSON required")
    if _validate_cik(raw.get("cik")) != _validate_cik(cik):
        raise ValueError("downloaded Company Facts CIK mismatch")
    return raw


def _canonical_bytes(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _load_json(path, max_bytes=MAX_JSON):
    with Path(path).open("rb") as handle:
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("JSON file too large")
    return json.loads(data)


def _atomic_write(path, content, *, overwrite=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=".investai_",
                                         delete=False) as stream:
            tmp = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if not overwrite and path.exists():
            if path.read_bytes() != content:
                raise ValueError("existing hash-named archive differs from expected bytes")
            tmp.unlink()
        else:
            os.replace(tmp, path)
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink()


def _mapping(ticker_data):
    """Official company_tickers.json dict (numbered records) or list."""
    if ticker_data is None:
        return None
    if isinstance(ticker_data, dict):
        rows = ticker_data.values()
    elif isinstance(ticker_data, list):
        rows = ticker_data
    else:
        raise ValueError("ticker map must be SEC records dict/list")
    mapping = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid SEC ticker-map row")
        ticker = row.get("ticker")
        if not isinstance(ticker, str):
            raise ValueError("missing SEC ticker")
        ticker = ticker.strip().upper()
        if not TICKER_PATTERN.fullmatch(ticker):
            raise ValueError("invalid SEC ticker label")
        cik = _validate_cik(row.get("cik_str"))
        if ticker in mapping and mapping[ticker] != cik:
            raise ValueError("ambiguous SEC ticker-to-CIK association: " + ticker)
        mapping[ticker] = cik
    if not mapping:
        raise ValueError("empty ticker map")
    return mapping


def resolve_universe(records, *, ticker_data=None, limit=100):
    _int(limit, "limit", 1, 500)
    if not isinstance(records, list) or not 1 <= len(records) <= limit:
        raise ValueError(f"universe must contain 1..{limit} companies")
    ticker_map = _mapping(ticker_data)
    out = []
    seen = set()
    for i, entry in enumerate(records):
        if not isinstance(entry, dict):
            raise ValueError(f"universe[{i}] is not an object")
        ticker = entry.get("ticker")
        if ticker is not None:
            if not isinstance(ticker, str) or not TICKER_PATTERN.fullmatch(ticker):
                raise ValueError(f"universe[{i}] has invalid ticker")
        provided_cik = entry.get("cik")
        if provided_cik is None and ticker is None:
            raise ValueError(f"universe[{i}] requires CIK or ticker")
        if ticker is not None and ticker_map is not None and ticker not in ticker_map:
            raise ValueError("ticker absent from supplied SEC mapping: " + ticker)
        mapped = ticker_map.get(ticker) if ticker_map is not None and ticker else None
        cik = _validate_cik(provided_cik) if provided_cik is not None else mapped
        if cik is None:
            raise ValueError("ticker-only entry requires an SEC ticker map: " + ticker)
        if mapped is not None and mapped != cik:
            raise ValueError("ticker CIK mismatch: " + ticker)
        if cik in seen:
            raise ValueError(f"duplicate CIK in universe: {cik}; share classes collapse to one SEC filer")
        seen.add(cik)
        sector = entry.get("sector", "unknown")
        if sector not in SECTORS:
            raise ValueError(f"universe[{i}] sector must be non_financial, financial or unknown")
        out.append({
            "cik": f"{cik:010d}", "ticker": ticker,
            "ticker_mapping_checked": mapped is not None,
            "sector": sector,
        })
    return out


class SECThrottle:
    """Sequential requests only. Does not coordinate other processes or IP users."""
    def __init__(self, *, interval=1.0, clock=time.monotonic, sleep=time.sleep):
        if (isinstance(interval, bool) or not isinstance(interval, (int, float))
                or not 0.5 <= interval <= 60):
            raise ValueError("minimum request interval must be 0.5..60 seconds")
        self.interval = interval
        self.clock = clock
        self.sleep = sleep
        self.last_request = None
        self.calls = 0

    def before_request(self):
        if self.last_request is not None:
            remaining = self.interval - (self.clock() - self.last_request)
            if remaining > 0:
                self.sleep(remaining)
        self.last_request = self.clock()
        self.calls += 1


def download_ticker_map(*, user_agent, limiter, opener=urllib.request.urlopen):
    if not isinstance(user_agent, str) or not re.search(r"\S+@\S+\.\S+", user_agent):
        raise ValueError("SEC_USER_AGENT must include an actual contact address")
    request = urllib.request.Request(TICKER_URL, headers={
        "User-Agent": user_agent, "Accept": "application/json",
        "Accept-Encoding": "identity"})
    limiter.before_request()
    try:
        with opener(request, timeout=20) as response:
            payload = response.read(MAX_TICKERS_JSON + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise StopSECRequests(f"SEC access restricted: HTTP {exc.code}") from exc
        raise
    if len(payload) > MAX_TICKERS_JSON:
        raise ValueError("SEC ticker map exceeds safe size")
    result = json.loads(payload)
    _mapping(result)
    return result


def _cached(archive_root, cik):
    """Read and VERIFY the latest saved SEC capture. Never trust index hashes."""
    root = Path(archive_root) / f"CIK{cik}"
    index = root / "index.json"
    if not index.exists():
        return None
    record = _load_json(index, max_bytes=2048)
    if (not isinstance(record, dict) or record.get("cik") != cik or
            record.get("source_url") != SEC_DATA.format(cik=int(cik))):
        raise ValueError("cache index has wrong issuer or source")
    digest = record.get("sha256")
    if not isinstance(digest, str) or not HASH_PATTERN.fullmatch(digest):
        raise ValueError("invalid archive hash")
    captured = record.get("captured_at_utc")
    if not isinstance(captured, str):
        raise ValueError("cache capture date absent")
    try:
        captured_at = dt.datetime.fromisoformat(captured)
    except ValueError as exc:
        raise ValueError("invalid cached timestamp") from exc
    if captured_at.tzinfo is None:
        raise ValueError("cache timestamp requires UTC timezone")
    snapshot = root / f"{digest}.json"
    content = snapshot.read_bytes()
    if hashlib.sha256(content).hexdigest() != digest:
        raise ValueError("SHA-256 archive integrity mismatch")
    data = json.loads(content)
    _check_doc(data, cik)
    return data, record, snapshot, captured_at


def _save_capture(archive_root, cik, raw, now):
    _check_doc(raw, cik)
    content = _canonical_bytes(raw)
    if len(content) > MAX_JSON:
        raise ValueError("SEC snapshot exceeds safe size")
    digest = hashlib.sha256(content).hexdigest()
    directory = Path(archive_root) / f"CIK{cik}"
    filename = directory / f"{digest}.json"
    _atomic_write(filename, content, overwrite=False)
    meta = {
        "cik": cik, "sha256": digest,
        "captured_at_utc": now.astimezone(dt.timezone.utc).isoformat(),
        "source_url": SEC_DATA.format(cik=int(cik)),
        "acquisition": "sec_direct_download",
        "immutable_snapshot": filename.name,
    }
    _atomic_write(directory / "index.json", _canonical_bytes(meta))
    return raw, meta, filename


def scan_universe(records, *, as_of, archive_dir, reports_dir, offline=False,
                  ticker_data=None, limit=100, max_age_hours=24,
                  user_agent="", min_interval_seconds=1.0,
                  downloader=download_companyfacts, clock=_utc,
                  limiter=None):
    """Analyze a bounded issuer universe, collecting errors per CIK.

    The 'complete' statuses are computational-eligibility markers only; no
    independent issuer source verification or price forecast is performed.
    """
    as_of = _iso_date(as_of)
    entries = resolve_universe(records, ticker_data=ticker_data, limit=limit)
    if isinstance(max_age_hours, bool) or not isinstance(max_age_hours, (int, float)) or not 0 <= max_age_hours <= 8760:
        raise ValueError("max_age_hours must be 0..8760")
    if not offline and (not isinstance(user_agent, str) or
                        not re.search(r"\S+@\S+\.\S+", user_agent)):
        raise ValueError("SEC_USER_AGENT with real contact required for online mode")
    limiter = limiter or SECThrottle(interval=min_interval_seconds)
    if Path(archive_dir).resolve() == Path(reports_dir).resolve():
        raise ValueError("archive_dir and reports_dir must be different")
    summary = {
        "version": VERSION, "as_of": as_of,
        "mode": "offline_cache" if offline else "sec_cached_or_direct",
        "ticker_map": "provided_snapshot" if ticker_data is not None else "not_provided",
        "ticker_map_sha256": (hashlib.sha256(_canonical_bytes(ticker_data)).hexdigest()
                              if ticker_data is not None else None),
        "status": "SCANNED_WITH_COVERAGE_LIMITATIONS",
        "records": [], "counts": {},
        "network_requests": 0,
        "warnings": [
            "The ticker mapping may be incomplete or outdated and is not historical ticker identity",
            "Sector classifications are supplied by an analyst, not verified by SEC SIC metadata",
            "A current SEC Company Facts download filtered by as_of is not a complete historical as-of snapshot",
            "Two agreeing TTM engines do not independently verify financial statement scope",
            "No pricing, automatic DCF, ranking or investment advice",
        ],
    }
    blocked = False
    for entry in entries:
        cik = entry["cik"]
        record = {
            "cik": cik, "ticker": entry["ticker"], "sector_assumption": entry["sector"],
            "ticker_mapping_checked": entry["ticker_mapping_checked"], "company": None,
            "status": None, "annual_audit": None, "fscore": None,
            "fscore_range": None, "ttm_status": None,
            "captured_at_utc": None, "snapshot_sha256": None,
            "snapshot_path": None, "research_json": None, "research_html": None,
            "error": None,
        }
        try:
            if blocked:
                record["status"] = "SKIPPED_SEC_ACCESS_RESTRICTION"
                summary["records"].append(record)
                continue
            cached = _cached(archive_dir, cik)
            now = clock()
            if now.tzinfo is None:
                raise ValueError("clock must return timezone-aware date")
            if cached:
                raw, meta, filename, captured_at = cached
                age_hours = (now - captured_at).total_seconds() / 3600
                if age_hours < -0.001:
                    raise ValueError("cache timestamp is later than the clock")
            if offline:
                if not cached:
                    record["status"] = "CACHE_MISS"
                    summary["records"].append(record)
                    continue
                record["status"] = "USED_CACHED"
            elif cached and 0 <= age_hours < max_age_hours:
                record["status"] = "USED_CACHED"
            else:
                limiter.before_request()
                try:
                    raw = downloader(int(cik), user_agent=user_agent)
                except urllib.error.HTTPError as exc:
                    if exc.code in (403, 429):
                        raise StopSECRequests(f"SEC access restricted: HTTP {exc.code}") from exc
                    raise
                _check_doc(raw, cik)
                raw, meta, filename = _save_capture(archive_dir, cik, raw, now)
                record["status"] = "DOWNLOADED"
            record["captured_at_utc"] = meta["captured_at_utc"]
            record["snapshot_sha256"] = meta["sha256"]
            record["snapshot_path"] = str(filename)

            research = build_company_research(raw, as_of=as_of,
                                               expected_cik=cik,
                                               sector=entry["sector"],
                                               input_mode="sec_direct_download")
            research["source"]["capture_timestamp_utc"] = meta["captured_at_utc"]
            research["source"]["snapshot_sha256"] = meta["sha256"]
            research["source"]["snapshot_file"] = str(filename)
            research["source"]["cache_used"] = record["status"] == "USED_CACHED"
            research["source"]["ticker_mapping_checked"] = entry["ticker_mapping_checked"]
            report_base = f"CIK{cik}_{as_of}_{meta['sha256'][:12]}"
            output_json = Path(reports_dir) / f"{report_base}.json"
            output_html = Path(reports_dir) / f"{report_base}.html"
            rendered = render_company_research(research)
            _atomic_write(output_json, _canonical_bytes(research))
            _atomic_write(output_html, rendered.encode("utf-8"))
            record["company"] = research["company"]
            record["annual_audit"] = research["annual_source_audit"]["status"]
            record["fscore"] = research["quality"]["piotroski"]["score"]
            record["fscore_range"] = research["quality"]["piotroski"]["score_range"]
            record["ttm_status"] = research["ttm_crosscheck"]["status"]
            record["research_json"] = str(output_json)
            record["research_html"] = str(output_html)
            record["status"] = ("ANALYZED_CONTROLS_COMPLETE" if
                                research["coverage_status"] == "ELIGIBLE_COMPONENT_MATH_COMPLETE"
                                else "ANALYZED_PARTIAL")
        except StopSECRequests as exc:
            blocked = True
            record["status"] = "SEC_ACCESS_RESTRICTED"
            record["error"] = str(exc)
        except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError,
                urllib.error.URLError) as exc:
            record["status"] = "INPUT_OR_ANALYSIS_ERROR"
            record["error"] = f"{type(exc).__name__}: {exc}"
        summary["records"].append(record)
    summary["counts"] = dict(sorted(Counter(x["status"] for x in summary["records"]).items()))
    summary["network_requests"] = limiter.calls
    summary["companies_requested"] = len(entries)
    summary["companies_analyzed"] = sum(x["status"].startswith("ANALYZED_") for x in summary["records"])
    summary["companies_with_errors"] = len(entries) - summary["companies_analyzed"]
    return summary


def _export(summary, json_path, csv_path):
    json_bytes = json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8")
    _atomic_write(json_path, json_bytes)
    import io
    buf = io.StringIO(newline="")
    columns = ("cik", "ticker", "company", "status", "sector_assumption",
               "ticker_mapping_checked", "annual_audit", "fscore", "fscore_range",
               "ttm_status", "captured_at_utc", "snapshot_sha256",
               "snapshot_path", "research_json", "research_html", "error")
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for entry in summary["records"]:
        line = {**entry, "fscore_range": json.dumps(entry["fscore_range"])}
        # SEC issuer names/error text can contain spreadsheet formulas.
        # Prefix dangerous leading characters when opened in Excel.
        for field, value in line.items():
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                line[field] = "'" + value
        writer.writerow(line)
    _atomic_write(csv_path, buf.getvalue().encode("utf-8-sig"))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="INVEST_AI bounded, SEC-compliant multi-issuer data collection and scan")
    parser.add_argument("--universe", required=True, help="JSON list of CIK/ticker records")
    parser.add_argument("--as-of", required=True, help="knowledge cutoff YYYY-MM-DD")
    parser.add_argument("--archive-dir", required=True, help="immutable SEC source captures")
    parser.add_argument("--reports-dir", required=True, help="per-company JSON and HTML")
    parser.add_argument("--out-json", required=True, help="aggregate manifest")
    parser.add_argument("--out-csv", required=True, help="aggregate table (UTF-8 BOM)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--offline", action="store_true", help="only cached SEC captures; no requests")
    mode.add_argument("--online", action="store_true", help="SEC downloads on cache miss/stale")
    ticker = parser.add_mutually_exclusive_group()
    ticker.add_argument("--ticker-map", help="locally archived SEC company_tickers.json")
    ticker.add_argument("--download-ticker-map", action="store_true",
                        help="one online SEC request for current ticker/CIK mapping")
    parser.add_argument("--ticker-map-out", help="required when downloading ticker map")
    parser.add_argument("--max-companies", type=int, default=100)
    parser.add_argument("--cache-ttl-hours", type=float, default=24)
    parser.add_argument("--minimum-request-interval", type=float, default=1.0)
    args = parser.parse_args(argv)
    if args.download_ticker_map and not args.online:
        parser.error("--download-ticker-map requires --online")
    if args.download_ticker_map and not args.ticker_map_out:
        parser.error("--download-ticker-map requires --ticker-map-out")
    if args.ticker_map_out and not args.download_ticker_map:
        parser.error("--ticker-map-out requires --download-ticker-map")
    if not args.universe or not Path(args.universe).is_file():
        parser.error("universe file does not exist")
    path_list = [Path(args.universe).resolve(), Path(args.out_json).resolve(),
                 Path(args.out_csv).resolve()]
    if args.ticker_map:
        path_list.append(Path(args.ticker_map).resolve())
    if args.ticker_map_out:
        path_list.append(Path(args.ticker_map_out).resolve())
    if len(set(path_list)) != len(path_list):
        parser.error("input and output files must have distinct paths")
    roots = [Path(args.archive_dir).resolve(), Path(args.reports_dir).resolve()]
    if roots[0] == roots[1] or any(p in roots for p in path_list):
        parser.error("archive/reports roots and input/output file paths must not overlap")
    entries = _load_json(args.universe, max_bytes=500000)
    _int(args.max_companies, "max_companies", 1, 500)
    limiter = SECThrottle(interval=args.minimum_request_interval)
    user_agent = os.getenv("SEC_USER_AGENT", "")
    if args.online and not re.search(r"\S+@\S+\.\S+", user_agent):
        parser.error("set SEC_USER_AGENT to application name and actual contact email")
    if args.download_ticker_map:
        ticker_data = download_ticker_map(user_agent=user_agent, limiter=limiter)
        _atomic_write(args.ticker_map_out, _canonical_bytes(ticker_data))
    elif args.ticker_map:
        ticker_data = _load_json(args.ticker_map, max_bytes=MAX_TICKERS_JSON)
    else:
        ticker_data = None
    # Validate full universe before the first Company Facts network request.
    resolve_universe(entries, ticker_data=ticker_data, limit=args.max_companies)
    summary = scan_universe(
        entries, as_of=args.as_of, archive_dir=args.archive_dir,
        reports_dir=args.reports_dir, offline=args.offline,
        ticker_data=ticker_data, limit=args.max_companies,
        max_age_hours=args.cache_ttl_hours, user_agent=user_agent,
        min_interval_seconds=args.minimum_request_interval, limiter=limiter)
    if args.ticker_map_out:
        summary["ticker_map_snapshot"] = str(Path(args.ticker_map_out))
    elif args.ticker_map:
        summary["ticker_map_snapshot"] = str(Path(args.ticker_map))
    else:
        summary["ticker_map_snapshot"] = None
    _export(summary, args.out_json, args.out_csv)
    print(json.dumps({k: v for k, v in summary.items() if k != "records"},
                     ensure_ascii=False, indent=2))
    return 0 if summary["companies_with_errors"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
