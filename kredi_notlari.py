"""Append-only manual long-term issuer ratings, independent of Piotroski/DCF.

Cited observations are not verified automatically against licensed feeds.
Never use issuer rating as a mechanically assigned discount rate.
"""
from __future__ import annotations
import datetime as dt
import pathlib
import sqlite3

VERSION = "credit-history-0.1.0"
MOODYS = ["Aaa", *[f"{x}{i}" for x in ("Aa", "A", "Baa", "Ba", "B", "Caa") for i in (1, 2, 3)], "Ca", "C"]
SP = ["AAA", *[x + s for x in ("AA", "A", "BBB", "BB", "B", "CCC") for s in ("+", "", "-")], "CC", "C", "D"]
SCALES = {"MOODYS": MOODYS, "S&P": SP, "FITCH": SP}
WITHDRAWN = {"MOODYS": "WR", "S&P": "NR", "FITCH": "WD"}
OUTLOOKS = {"positive", "stable", "negative", "developing", "review", "not_stated"}

def _date(value):
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("expected ISO YYYY-MM-DD") from None

def _nonempty(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}: nonempty text required")
    return value.strip()

class CreditRatingLedger:
    """Source-backed, local, append-only rating-event ledger for issuer CIK."""
    def __init__(self, path):
        self.db = sqlite3.connect(str(pathlib.Path(path)))
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS rating_events (
            id INTEGER PRIMARY KEY,
            cik TEXT NOT NULL, issuer_name TEXT NOT NULL, agency TEXT NOT NULL,
            rating TEXT NOT NULL, outlook TEXT NOT NULL,
            rating_scope TEXT NOT NULL CHECK(rating_scope='long_term_issuer'),
            effective_date TEXT NOT NULL, published_date TEXT NOT NULL,
            recorded_at TEXT NOT NULL, source_url TEXT NOT NULL,
            review_note TEXT NOT NULL,
            UNIQUE(cik,agency,rating,outlook,rating_scope,
                   effective_date,published_date,source_url)
        );
        CREATE TRIGGER IF NOT EXISTS rating_no_update BEFORE UPDATE ON rating_events
        BEGIN SELECT RAISE(ABORT,'append only'); END;
        CREATE TRIGGER IF NOT EXISTS rating_no_delete BEFORE DELETE ON rating_events
        BEGIN SELECT RAISE(ABORT,'append only'); END;
        """)
        self.db.commit()

    def __enter__(self): return self
    def __exit__(self, *_): self.db.close()

    def add(self, *, cik, issuer_name, agency, rating, outlook, effective_date,
            published_date, source_url, review_note, rating_scope="long_term_issuer"):
        from sec_companyfacts import _validate_cik
        number = f"{_validate_cik(cik):010d}"
        _nonempty(issuer_name, "issuer_name")
        agency = _nonempty(agency, "agency")
        if agency not in SCALES or (rating not in SCALES[agency] and rating != WITHDRAWN[agency]):
            raise ValueError("unsupported agency/rating combination")
        if outlook not in OUTLOOKS:
            raise ValueError("unsupported rating outlook")
        if rating_scope != "long_term_issuer":
            raise ValueError("only long-term issuer ratings accepted; do not mix issue/subsidiary ratings")
        effective, published = _date(effective_date), _date(published_date)
        if published < effective - dt.timedelta(days=5):
            raise ValueError("publication substantially precedes rating event")
        if not isinstance(source_url, str) or not source_url.startswith("https://"):
            raise ValueError("HTTPS source URL required")
        if len(_nonempty(review_note, "review_note")) < 12:
            raise ValueError("specific review note required")
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        with self.db:
            cursor = self.db.execute("""
              INSERT INTO rating_events
              (cik,issuer_name,agency,rating,outlook,rating_scope,
               effective_date,published_date,recorded_at,source_url,review_note)
              VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                                     (number, issuer_name, agency, rating, outlook, rating_scope,
                                      effective.isoformat(), published.isoformat(), now, source_url, review_note))
        return cursor.lastrowid

    def as_of(self, cik, as_of):
        from sec_companyfacts import _validate_cik
        number = f"{_validate_cik(cik):010d}"
        cutoff = _date(as_of).isoformat()
        rows = self.db.execute("""
          SELECT id,cik,issuer_name,agency,rating,outlook,rating_scope,
                 effective_date,published_date,recorded_at,source_url,review_note
          FROM rating_events
          WHERE cik=? AND effective_date<=? AND published_date<=?
          ORDER BY agency,effective_date DESC,published_date DESC,id DESC""",
                               (number, cutoff, cutoff)).fetchall()
        columns = ("id", "cik", "issuer_name", "agency", "rating", "outlook",
                   "rating_scope", "effective_date", "published_date", "recorded_at",
                   "source_url", "review_note")
        records = {}
        for raw in rows:
            item = dict(zip(columns, raw))
            records.setdefault(item["agency"], item)
        for item in records.values():
            scale = SCALES[item["agency"]]
            boundary = "Baa3" if item["agency"] == "MOODYS" else "BBB-"
            item["withdrawn_or_unrated"] = item["rating"] == WITHDRAWN[item["agency"]]
            item["investment_grade"] = (None if item["withdrawn_or_unrated"]
                                        else scale.index(item["rating"]) <= scale.index(boundary))
            item["source_verified_automatically"] = False
        return {
          "version": VERSION, "cik": number, "as_of": cutoff,
          "agency_ratings": records, "available_agencies": sorted(records),
          "status": "available" if records else "not_available",
          "notes": [
              "Issuer-level long-term rating only; exclude issue, parent, subsidiary and sovereign ratings",
              "Source descriptions are manually supplied, not automatically authenticated",
              "A withdrawn rating does not retain its old active grade",
              "No automatic WACC, stock-price, valuation or Piotroski score mapping"]}

def company_quality_snapshot(companyfacts, *, as_of, sector="unknown",
                             equity_offering_evidence=None, credit_db=None):
    from piotroski_fscore import compute_piotroski
    p = compute_piotroski(companyfacts, as_of=as_of, sector=sector,
                          equity_offering_evidence=equity_offering_evidence)
    c = None
    if credit_db is not None:
        with CreditRatingLedger(credit_db) as db:
            c = db.as_of(p["cik"], as_of)
    return {"company": p["company"], "cik": p["cik"], "as_of": as_of,
            "piotroski": p, "credit": c, "combined_score": None,
            "warning": "These are distinct financial-strength and default-risk lenses; not an investment recommendation"}
