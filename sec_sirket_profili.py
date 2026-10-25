"""INVEST_AI — SEC issuer profiles: SIC industry code, entity type and exchanges.

Company Facts carries no industry. SEC's nightly bulk `submissions.zip` holds
every filer's registration profile (SIC code and description, entity type,
listed exchanges). One request downloads it; profiles of the issuers already in
the screener database are read from the ZIP without extracting it.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import zipfile

from sec_piyasa_toplu_tarama import DB_REL as SCREEN_DB_REL, ZIP_NAME, fetch_bulk_zip

SUBMISSIONS_URL = "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"
ZIP_REL = "veri/submissions.zip"
DB_REL = "veri/sec_sirket_profili.sqlite3"
MAX_MEMBER_BYTES = 40_000_000
# SIC divisions (SEC / OSHA Standard Industrial Classification), Turkish labels.
DIVISIONS = (
    (100, 999, "Tarım, ormancılık, balıkçılık"), (1000, 1499, "Madencilik ve enerji üretimi"),
    (1500, 1799, "İnşaat"), (2000, 3999, "İmalat"),
    (4000, 4999, "Ulaştırma, iletişim, elektrik-gaz-su"), (5000, 5199, "Toptan ticaret"),
    (5200, 5999, "Perakende"), (6000, 6799, "Finans, sigorta, gayrimenkul"),
    (7000, 8999, "Hizmetler"), (9100, 9729, "Kamu yönetimi"), (9900, 9999, "Sınıflandırılmamış"),
)


def sic_division(sic):
    if not isinstance(sic, int):
        return "Bilinmiyor"
    return next((label for low, high, label in DIVISIONS if low <= sic <= high), "Bilinmiyor")


def is_financial(sic):
    """Banks, credit, brokers, insurers, real-estate trusts and blank-check holding companies."""
    return isinstance(sic, int) and 6000 <= sic <= 6799


def parse_profile(raw):
    """The fields INVEST_AI uses from one SEC submissions JSON; None if it is not a filer profile."""
    if not isinstance(raw, dict):
        return None
    try:
        cik = f"{int(raw.get('cik')):010d}"
    except (TypeError, ValueError):
        return None
    try:
        sic = int(str(raw.get("sic") or "").strip())
    except ValueError:
        sic = None

    def text(value, limit):
        return str(value).strip()[:limit] if value not in (None, "") else None
    # SEC aligns tickers[i] with exchanges[i]; keep the pairs, an exchange may be empty.
    raw_tickers, raw_exchanges = raw.get("tickers") or [], raw.get("exchanges") or []
    pairs = [(str(t).strip().upper(), str(raw_exchanges[i] or "").strip() if i < len(raw_exchanges) else "")
             for i, t in enumerate(raw_tickers) if t]
    return {"cik": cik, "name": text(raw.get("name"), 300), "sic": sic,
            "sic_description": text(raw.get("sicDescription"), 200), "division": sic_division(sic),
            "financial": is_financial(sic), "entity_type": text(raw.get("entityType"), 60),
            "category": text(raw.get("category"), 120),
            "exchanges": ",".join(e for _, e in pairs if e)[:200] or None,
            "tickers": ",".join(t for t, _ in pairs)[:200] or None,
            "listings": ",".join(f"{t}:{e}" for t, e in pairs)[:300] or None,
            "fiscal_year_end": text(raw.get("fiscalYearEnd"), 8)}


# Exchanges where common stock trades on a listed market (not over the counter).
LISTED_EXCHANGES = ("NYSE", "Nasdaq", "NYSE American", "NYSE MKT", "NYSE Arca", "CBOE", "BATS")


def primary_ticker(profile, fallback=None):
    """The issuer's listed ticker: first SEC listing on a listed exchange, else its first ticker."""
    listings = [item.rsplit(":", 1) for item in ((profile or {}).get("listings") or "").split(",") if item]
    for ticker, exchange in listings:
        if exchange in LISTED_EXCHANGES:
            return ticker
    return listings[0][0] if listings else fallback


def _connect(db):
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS profiles (
            cik TEXT PRIMARY KEY, name TEXT, sic INTEGER, sic_description TEXT, division TEXT,
            financial INTEGER, entity_type TEXT, category TEXT, exchanges TEXT, tickers TEXT,
            listings TEXT, fiscal_year_end TEXT, source TEXT NOT NULL, imported_utc TEXT NOT NULL
        );
    """)
    return conn


def _screen_ciks(root):
    db = Path(root).resolve() / SCREEN_DB_REL
    if not db.is_file():
        raise FileNotFoundError("Run the SEC bulk screener first: no local issuer database")
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as conn:
        return [cik for (cik,) in conn.execute("SELECT cik FROM companies ORDER BY cik")]


def import_profiles(root, *, archive_path=None, progress=None):
    """Read the profile of every issuer in the screener database from a local submissions.zip."""
    root = Path(root).resolve()
    archive = Path(archive_path).resolve() if archive_path else root / ZIP_REL
    if not archive.is_file():
        raise FileNotFoundError("Missing SEC submissions.zip; download it first")
    wanted = set(_screen_ciks(root))
    stamp = datetime.now(timezone.utc).isoformat()
    source = f"SEC submissions.zip ({archive.stat().st_size} bytes, {archive.name})"
    found, skipped = [], {}
    with zipfile.ZipFile(archive) as source_zip:
        members = {}
        for meta in source_zip.infolist():
            match = ZIP_NAME.search(meta.filename)   # CIK##########.json, not the -submissions-NNN overflow files
            if match and match.group(1) in wanted:
                members[match.group(1)] = meta
        for number, (cik, meta) in enumerate(sorted(members.items()), start=1):
            if meta.file_size > MAX_MEMBER_BYTES:
                skipped["TOO_LARGE"] = skipped.get("TOO_LARGE", 0) + 1
                continue
            with source_zip.open(meta) as handle:
                profile = parse_profile(json.loads(handle.read()))
            if profile is None or profile["cik"] != cik:
                skipped["CIK_MISMATCH_OR_INVALID"] = skipped.get("CIK_MISMATCH_OR_INVALID", 0) + 1
                continue
            found.append(dict(profile, financial=int(profile["financial"]), source=source, imported_utc=stamp))
            if progress and number % 500 == 0:
                progress({"phase": "profiles", "read": number, "total": len(members)})
    # Every import rebuilds the table from the ZIP, so a newer column layout needs no migration.
    (root / DB_REL).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(root / DB_REL)) as conn, conn:
        conn.execute("DROP TABLE IF EXISTS profiles")
    with closing(_connect(root / DB_REL)) as conn, conn:
        conn.executemany(
            "INSERT OR REPLACE INTO profiles VALUES(:cik,:name,:sic,:sic_description,:division,:financial,"
            ":entity_type,:category,:exchanges,:tickers,:listings,:fiscal_year_end,:source,:imported_utc)", found)
    return {"issuers": len(wanted), "profiles": len(found), "not_in_zip": len(wanted) - len(members),
            "skipped": skipped, "database": DB_REL}


def load_profiles(root):
    db = Path(root).resolve() / DB_REL
    if not db.is_file():
        return {}
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        return {r["cik"]: dict(r, financial=bool(r["financial"])) for r in conn.execute("SELECT * FROM profiles")}


def main(argv=None):
    parser = argparse.ArgumentParser(description="SEC issuer profiles (SIC industry, exchanges) for the screener")
    parser.add_argument("--root", default=".", help="INVEST_AI checkout root")
    parser.add_argument("--zip", help="use an already downloaded submissions.zip")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    archive = Path(args.zip).resolve() if args.zip else root / ZIP_REL

    def status(info):
        print(json.dumps(info, ensure_ascii=False), flush=True)
    if not archive.is_file():
        fetch_bulk_zip(archive, user_agent=os.getenv("SEC_USER_AGENT", ""), progress=status, url=SUBMISSIONS_URL)
    print(json.dumps(import_profiles(root, archive_path=archive, progress=status), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    main()
