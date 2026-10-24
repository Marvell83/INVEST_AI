"""INVEST_AI — shared SEC Company Facts archive and request helpers.

Standard library only. Used by the batch scanner, the local web server and the
change monitor so that none of them imports another module's private helpers.
Immutable content-hash snapshots; a mutable index identifies the last capture.
Rate limiter is per PROCESS, not global to an IP or multiple machines.
"""
from __future__ import annotations

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

from sec_companyfacts import SEC_DATA, _validate_cik

TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")
HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
MAX_JSON = 50_000_000
MAX_TICKERS_JSON = 12_000_000


class StopSECRequests(Exception):
    """An access-control response stops ALL remaining external SEC requests."""


def iso_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("as_of must be YYYY-MM-DD")
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("invalid as_of calendar date") from exc
    return value


def check_doc(raw, cik):
    if not isinstance(raw, dict) or not isinstance(raw.get("facts"), dict):
        raise ValueError("raw SEC Company Facts JSON required")
    if _validate_cik(raw.get("cik")) != _validate_cik(cik):
        raise ValueError("downloaded Company Facts CIK mismatch")
    return raw


def canonical_bytes(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def load_json(path, max_bytes=MAX_JSON):
    with Path(path).open("rb") as handle:
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("JSON file too large")
    return json.loads(data)


def atomic_write(path, content, *, overwrite=True):
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


def ticker_mapping(ticker_data):
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
    ticker_mapping(result)
    return result


def cached_capture(archive_root, cik):
    """Read and VERIFY the latest saved SEC capture. Never trust index hashes."""
    root = Path(archive_root) / f"CIK{cik}"
    index = root / "index.json"
    if not index.exists():
        return None
    record = load_json(index, max_bytes=2048)
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
    check_doc(data, cik)
    return data, record, snapshot, captured_at


def save_capture(archive_root, cik, raw, now):
    check_doc(raw, cik)
    content = canonical_bytes(raw)
    if len(content) > MAX_JSON:
        raise ValueError("SEC snapshot exceeds safe size")
    digest = hashlib.sha256(content).hexdigest()
    directory = Path(archive_root) / f"CIK{cik}"
    filename = directory / f"{digest}.json"
    atomic_write(filename, content, overwrite=False)
    meta = {
        "cik": cik, "sha256": digest,
        "captured_at_utc": now.astimezone(dt.timezone.utc).isoformat(),
        "source_url": SEC_DATA.format(cik=int(cik)),
        "acquisition": "sec_direct_download",
        "immutable_snapshot": filename.name,
    }
    atomic_write(directory / "index.json", canonical_bytes(meta))
    return raw, meta, filename
