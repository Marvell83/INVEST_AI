"""Immutable, local SQLite forecast ledger for INVEST_AI.

Standard library only. Forecasts are append-only; outcomes and evaluations
are separate records. No investment recommendation or live market data.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

def _json(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name}: finite number required")
    return float(value)

class TahminDefteri:
    def __init__(self, path):
        self.path = str(Path(path))
        self.db = sqlite3.connect(self.path)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS forecasts(
            id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL,
            company TEXT NOT NULL,
            metric TEXT NOT NULL,
            target_period TEXT NOT NULL,
            currency TEXT NOT NULL,
            predicted REAL NOT NULL,
            model_version TEXT NOT NULL,
            assumptions_json TEXT NOT NULL,
            sources_json TEXT NOT NULL,
            digest TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS outcomes(
            id INTEGER PRIMARY KEY,
            recorded_at TEXT NOT NULL,
            company TEXT NOT NULL,
            metric TEXT NOT NULL,
            target_period TEXT NOT NULL,
            currency TEXT NOT NULL,
            actual REAL NOT NULL,
            source TEXT NOT NULL,
            UNIQUE(company, metric, target_period, currency, source)
        );
        CREATE TABLE IF NOT EXISTS evaluations(
            id INTEGER PRIMARY KEY,
            evaluated_at TEXT NOT NULL,
            forecast_id INTEGER NOT NULL REFERENCES forecasts(id),
            outcome_id INTEGER NOT NULL REFERENCES outcomes(id),
            absolute_error REAL NOT NULL,
            signed_error REAL NOT NULL,
            UNIQUE(forecast_id, outcome_id)
        );
        CREATE TRIGGER IF NOT EXISTS forecasts_no_update BEFORE UPDATE ON forecasts
            BEGIN SELECT RAISE(ABORT, 'forecasts are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS forecasts_no_delete BEFORE DELETE ON forecasts
            BEGIN SELECT RAISE(ABORT, 'forecasts are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS outcomes_no_update BEFORE UPDATE ON outcomes
            BEGIN SELECT RAISE(ABORT, 'outcomes are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS outcomes_no_delete BEFORE DELETE ON outcomes
            BEGIN SELECT RAISE(ABORT, 'outcomes are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS evaluations_no_update BEFORE UPDATE ON evaluations
            BEGIN SELECT RAISE(ABORT, 'evaluations are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS evaluations_no_delete BEFORE DELETE ON evaluations
            BEGIN SELECT RAISE(ABORT, 'evaluations are immutable'); END;
        """)
        self.db.commit()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self.db.close()

    def tahmin_kaydet(self, *, company, metric, target_period, currency,
                      predicted, model_version, assumptions, sources):
        for name, value in (("company", company), ("metric", metric),
                            ("target_period", target_period), ("currency", currency),
                            ("model_version", model_version)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name}: nonempty string required")
        if not isinstance(sources, list) or not sources or not all(isinstance(s, str) and s.strip() for s in sources):
            raise ValueError("sources: nonempty list of citations required")
        predicted = _number(predicted, "predicted")
        payload = dict(company=company, metric=metric, target_period=target_period,
                       currency=currency, predicted=predicted, model_version=model_version,
                       assumptions=assumptions, sources=sources)
        digest = hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()
        with self.db:
            cur = self.db.execute("""
                INSERT INTO forecasts(created_at, company, metric, target_period,
                currency, predicted, model_version, assumptions_json, sources_json, digest)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (_now(), company, metric, target_period, currency, predicted,
                 model_version, _json(assumptions), _json(sources), digest))
        return cur.lastrowid

    def gerceklesen_kaydet(self, *, company, metric, target_period, currency, actual, source):
        for name, value in (("company", company), ("metric", metric),
                            ("target_period", target_period), ("currency", currency), ("source", source)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name}: nonempty string required")
        actual = _number(actual, "actual")
        with self.db:
            cur = self.db.execute("""
                INSERT INTO outcomes(recorded_at, company, metric, target_period,
                currency, actual, source) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (_now(), company, metric, target_period, currency, actual, source))
        return cur.lastrowid

    def puanla(self, forecast_id, outcome_id):
        f = self.db.execute("SELECT company, metric, target_period, currency, predicted FROM forecasts WHERE id=?", (forecast_id,)).fetchone()
        o = self.db.execute("SELECT company, metric, target_period, currency, actual FROM outcomes WHERE id=?", (outcome_id,)).fetchone()
        if f is None or o is None:
            raise ValueError("forecast or outcome not found")
        if f[:4] != o[:4]:
            raise ValueError("company/metric/period/currency mismatch")
        signed = f[4] - o[4]
        with self.db:
            cur = self.db.execute("""
                INSERT INTO evaluations(evaluated_at, forecast_id, outcome_id, absolute_error, signed_error)
                VALUES (?, ?, ?, ?, ?)""",
                (_now(), forecast_id, outcome_id, abs(signed), signed))
        return dict(id=cur.lastrowid, absolute_error=abs(signed), signed_error=signed)

    def tahminleri_listele(self):
        rows = self.db.execute("""
            SELECT id, created_at, company, metric, target_period, currency,
                   predicted, model_version, digest FROM forecasts ORDER BY id""").fetchall()
        keys = ("id", "created_at", "company", "metric", "target_period",
                "currency", "predicted", "model_version", "digest")
        return [dict(zip(keys, row)) for row in rows]
