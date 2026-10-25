"""INVEST_AI v0.3: authenticated local web research (Python stdlib only).

A local browser POST executes SEC/TTM/financial-statements engines and, when the
analyst supplies sourced rates, the scenario projection and scenario DCF.
Requires a session API key printed in the terminal, no user-facing shell input,
no trading. SEC requests are serialised/throttled and archived with a content hash.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import threading
import urllib.error
from urllib.parse import unquote, urlsplit

from sec_companyfacts import download_companyfacts
from sec_arsiv import (
    SECThrottle, StopSECRequests, atomic_write, cached_capture, canonical_bytes,
    check_doc, download_ticker_map, load_json, save_capture, ticker_mapping,
)
from senaryo_degerleme import DISCOUNT_BOUNDS, TERMINAL_GROWTH_CAP
from sirket_arastirma_akisi import build_company_research, render_company_research
from tahmin_motoru import LONG_RUN_BOUNDS

ROOT = Path(__file__).resolve().parent
VERSION = "invest-ai-web-0.4.0"
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")
EMAIL_RE = re.compile(r"\S+@\S+\.\S+")
MODES = ("demo", "live", "cache")
SECTORS = ("non_financial", "financial", "unknown")
REQUIRED_FIELDS = frozenset(("ticker", "mode", "sector"))
# Optional analyst inputs: each rate travels with its citation.
SCENARIO_FIELDS = ("long_run_growth", "long_run_growth_source", "discount_rate", "discount_rate_source",
                   "market_price", "market_price_date", "market_price_source")
SOURCE_LENGTH = (8, 300)
MAX_BODY_BYTES = 4096
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SEC_LIST_PAGE_SIZE = 50
SEC_LIST_MAX_SEARCH_LENGTH = 80


def _price_inputs(values, today):
    """An analyst-entered, dated and cited price for the reverse DCF; never downloaded."""
    names = ("market_price", "market_price_date", "market_price_source")
    given = [values[n] is not None for n in names]
    if not any(given):
        return
    if not all(given):
        raise RequestError("Fiyat, fiyat tarihi ve fiyatın kaynağı birlikte girilmeli.")
    if values["discount_rate"] is None:
        raise RequestError("Ters DCF için önce büyüme ve iskonto girdileri gerekli.")
    price = values["market_price"]
    if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or not 0 < price <= 1e6:
        raise RequestError("Fiyat 0'dan büyük, en fazla 1.000.000 USD olmalı.")
    date = values["market_price_date"]
    try:
        quoted = datetime.strptime(date, "%Y-%m-%d").date() if isinstance(date, str) and DATE_RE.match(date) else None
    except ValueError:
        quoted = None
    if quoted is None or quoted > today:
        raise RequestError("Fiyat tarihi YYYY-AA-GG biçiminde ve bugünden ileri olmayan bir tarih olmalı.")
    text = values["market_price_source"]
    if not isinstance(text, str) or not SOURCE_LENGTH[0] <= len(text.strip()) <= SOURCE_LENGTH[1]:
        raise RequestError(f"Fiyat kaynağı {SOURCE_LENGTH[0]}–{SOURCE_LENGTH[1]} karakter olmalı.")
    values["market_price_source"] = text.strip()


def _scenario_inputs(request, today):
    """Validate optional scenario / valuation inputs; the system never fills them in."""
    values = {name: request.get(name) for name in SCENARIO_FIELDS}
    for rate, source, (low, high), label in (
            ("long_run_growth", "long_run_growth_source", LONG_RUN_BOUNDS, "Uzun vadeli büyüme"),
            ("discount_rate", "discount_rate_source", DISCOUNT_BOUNDS, "İskonto oranı")):
        if (values[rate] is None) != (values[source] is None):
            raise RequestError(f"{label} ve kaynağı birlikte girilmeli.")
        if values[rate] is None:
            continue
        value = values[rate]
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                or not low <= value <= high):
            raise RequestError(f"{label} %{low * 100:g} ile %{high * 100:g} arasında olmalı.")
        text = values[source]
        if not isinstance(text, str) or not SOURCE_LENGTH[0] <= len(text.strip()) <= SOURCE_LENGTH[1]:
            raise RequestError(f"{label} kaynağı {SOURCE_LENGTH[0]}–{SOURCE_LENGTH[1]} karakter olmalı.")
        values[source] = text.strip()
    if values["discount_rate"] is not None:
        if values["long_run_growth"] is None:
            raise RequestError("Değerleme için önce uzun vadeli büyüme ve kaynağı girilmeli.")
        if values["long_run_growth"] > TERMINAL_GROWTH_CAP:
            raise RequestError(f"Değerlemede uzun vadeli büyüme en fazla %{TERMINAL_GROWTH_CAP * 100:g} "
                               "olabilir (sonsuz büyüme tavanı).")
    _price_inputs(values, today)
    return values


class RequestError(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


class ResearchService:
    def __init__(self, root=ROOT, *, secret=None, user_agent=None,
                 ticker_download=download_ticker_map, fact_download=download_companyfacts,
                 clock=None, throttle=None):
        self.root = Path(root).resolve()
        self.secret = secret or secrets.token_urlsafe(32)
        if not isinstance(self.secret, str) or len(self.secret) < 24:
            raise ValueError("Web secret must be at least 24 characters")
        self.user_agent = user_agent if user_agent is not None else os.getenv("SEC_USER_AGENT", "")
        self.ticker_download = ticker_download
        self.fact_download = fact_download
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.throttle = throttle or SECThrottle(interval=1.0)
        self.lock = threading.Lock()
        self.sec_blocked = False

    def _online_ok(self):
        if self.sec_blocked:
            raise RequestError("SEC erişim engeli kaydedildi. Canlı istekler bu oturumda durduruldu.", 503)
        if not EMAIL_RE.search(self.user_agent or ""):
            raise RequestError("Canlı kullanım için sunucuyu gerçek iletişim adresiyle SEC_USER_AGENT tanımlayarak aç.", 422)

    def _ticker_map(self, mode):
        path = self.root / "veri/sec_ticker_esleme.json"
        if mode == "cache":
            if not path.is_file():
                raise RequestError("Yerel SEC ticker haritası yok; önce 'Güncel SEC' seç.", 404)
            return ticker_mapping(load_json(path, max_bytes=12_000_000)), "SAVED_SEC_MAP"
        if path.is_file():
            age_seconds = self.clock().timestamp() - path.stat().st_mtime
            if mode == "live" and 0 <= age_seconds < 24 * 3600:
                return ticker_mapping(load_json(path, max_bytes=12_000_000)), "CACHED_SEC_MAP"
        self._online_ok()
        try:
            source = self.ticker_download(user_agent=self.user_agent, limiter=self.throttle)
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429):
                self.sec_blocked = True
            raise RequestError(f"SEC ticker eşleme HTTP {exc.code}", 503) from exc
        except StopSECRequests as exc:
            self.sec_blocked = True
            raise RequestError(str(exc), 503) from exc
        table = ticker_mapping(source)
        atomic_write(path, canonical_bytes(source))
        return table, "DOWNLOADED_SEC_MAP"


    def scan_sec_list(self, request):
        """List SEC ticker/CIK directory; does not download financial statements."""
        if not isinstance(request, dict) or not set(request) <= {"query", "offset", "refresh"}:
            raise RequestError("SEC liste isteği geçersiz.")
        query = request.get("query", "")
        offset = request.get("offset", 0)
        refresh = request.get("refresh", False)
        if not isinstance(query, str) or len(query) > SEC_LIST_MAX_SEARCH_LENGTH:
            raise RequestError("Arama en fazla 80 karakter olmalı.")
        if type(offset) is not int or not 0 <= offset <= 100000 or type(refresh) is not bool:
            raise RequestError("Sayfa veya güncelleme isteği geçersiz.")
        if not self.lock.acquire(blocking=False):
            raise RequestError("Bir SEC işlemi çalışıyor. Daha sonra tekrar dene.", 409)
        try:
            path = self.root / "veri/sec_ticker_esleme.json"
            if refresh or not path.is_file():
                self._online_ok()
                try:
                    source = self.ticker_download(user_agent=self.user_agent, limiter=self.throttle)
                except urllib.error.HTTPError as exc:
                    if exc.code in (403, 429):
                        self.sec_blocked = True
                    raise RequestError(f"SEC şirket listesi HTTP {exc.code}", 503) from exc
                except urllib.error.URLError as exc:
                    raise RequestError("SEC şirket listesi indirilemedi.", 503) from exc
                except StopSECRequests as exc:
                    self.sec_blocked = True
                    raise RequestError(str(exc), 503) from exc
                ticker_mapping(source)
                atomic_write(path, canonical_bytes(source))
                source_label = "SEC_DOWNLOAD"
            else:
                source_label = "SAVED_SEC_MAP"
            raw = load_json(path, max_bytes=12_000_000)
            mapping = ticker_mapping(raw)
            values = raw.values() if isinstance(raw, dict) else raw
            names = {}
            for row in values:
                ticker = row["ticker"].strip().upper()
                title = row.get("title", "")
                names[ticker] = title[:300] if isinstance(title, str) else ""
            records = sorted(
                ({"ticker": ticker, "company": names.get(ticker, ""),
                  "cik": f"{cik:010d}"} for ticker, cik in mapping.items()),
                key=lambda row: (row["ticker"], row["cik"]))
            term = query.strip().casefold()
            if term:
                records = [row for row in records if term in row["ticker"].casefold()
                           or term in row["company"].casefold() or term in row["cik"]]
            matched = len(records)
            return {"ok": True, "source": source_label, "total": len(mapping),
                    "matched": matched, "offset": offset, "limit": SEC_LIST_PAGE_SIZE,
                    "rows": records[offset:offset + SEC_LIST_PAGE_SIZE],
                    "has_more": offset + SEC_LIST_PAGE_SIZE < matched,
                    "snapshot_updated_utc": datetime.fromtimestamp(
                        path.stat().st_mtime, tz=timezone.utc).isoformat(),
                    "data_scope": "SEC_TICKER_CIK_DIRECTORY_ONLY",
                    "financial_facts_downloaded": False}
        finally:
            self.lock.release()

    def analyze(self, request):
        if (not isinstance(request, dict) or not REQUIRED_FIELDS <= set(request)
                or not set(request) <= REQUIRED_FIELDS | set(SCENARIO_FIELDS)):
            raise RequestError("ticker, mode ve sector alanları gerekir.")
        ticker, mode, sector = request["ticker"], request["mode"], request["sector"]
        if not isinstance(ticker, str):
            raise RequestError("Hisse sembolü metin olmalı.")
        ticker = ticker.strip().upper()
        if not TICKER_RE.fullmatch(ticker) or mode not in MODES or sector not in SECTORS:
            raise RequestError("Ticker, veri türü veya sektör geçersiz.")
        scenario = _scenario_inputs(request, self.clock().date())
        if not self.lock.acquire(blocking=False):
            raise RequestError("Bir analiz çalışıyor. Bittikten sonra yeniden dene.", 409)
        try:
            return self._run(ticker, mode, sector, scenario)
        finally:
            self.lock.release()

    def _run(self, ticker, mode, sector, scenario=None):
        scenario = scenario or dict.fromkeys(SCENARIO_FIELDS)
        if mode == "demo":
            if ticker != "AAPL":
                raise RequestError("Örnek veri yalnız AAPL içindir. Başka şirket için Güncel SEC seç.")
            cik = 320193
            as_of = "2026-10-21"
            raw = load_json(self.root / "ornekler/apple_ttm_evidence_2026-10-21.json")
            check_doc(raw, cik)
            source = "MANUAL_APPLE_EXAMPLE_NOT_LIVE_SEC"
            archive = None
            mapping_source = "EXAMPLE_FIXED_CIK"
        else:
            ticker_map, mapping_source = self._ticker_map(mode)
            if ticker not in ticker_map:
                raise RequestError("SEC ticker listesinde şirket bulunamadı: " + ticker, 404)
            cik = ticker_map[ticker]
            if mode == "cache":
                cached = cached_capture(self.root / "veri/sec_kaynaklari", f"{cik:010d}")
                if cached is None:
                    raise RequestError("Bu şirketin yerel SEC arşivi henüz yok.", 404)
                raw, _, archive, _ = cached
                source = "LOCAL_SHA256_VERIFIED_NOT_SEC_IDENTITY_VERIFIED"
            else:
                self._online_ok()
                self.throttle.before_request()
                try:
                    raw = self.fact_download(cik, user_agent=self.user_agent)
                except urllib.error.HTTPError as exc:
                    if exc.code in (403, 429):
                        self.sec_blocked = True
                    raise RequestError(f"SEC Company Facts HTTP {exc.code}", 503) from exc
                except urllib.error.URLError as exc:
                    raise RequestError("SEC bağlantısı kurulamadı.", 503) from exc
                check_doc(raw, cik)
                _, _, archive = save_capture(self.root / "veri/sec_kaynaklari",
                                             f"{cik:010d}", raw, self.clock())
                source = "SEC_DIRECT_DOWNLOAD_UNVERIFIED_INDEPENDENTLY"
            as_of = self.clock().date().isoformat()

        result = build_company_research(raw, expected_cik=cik, as_of=as_of,
                                        sector=sector, include_piotroski=False,
                                        input_mode="sec_direct_download" if mode == "live" else "offline_file",
                                        **scenario)
        result["source"]["web_data_mode"] = mode
        result["source"]["web_source_label"] = source
        result["source"]["ticker_map_provenance"] = mapping_source
        result["source"]["archive_path"] = archive.relative_to(self.root).as_posix() if archive else None
        page = render_company_research(result)
        digest = result["source"]["canonical_json_sha256"][:12]
        # A different analyst sector assumption must not overwrite an earlier report
        # generated from the same SEC snapshot with another classification.
        basename = f"{ticker}_{mode.upper()}_{as_of}_{sector}_{digest}_fundamentals"
        if any(value is not None for value in scenario.values()):
            # Different analyst scenario inputs must not overwrite each other either.
            basename += "_s" + hashlib.sha256(canonical_bytes(scenario)).hexdigest()[:8]
        folder = self.root / "reports" / "research"
        out_json = folder / (basename + ".json")
        out_html = folder / (basename + ".html")
        atomic_write(out_json, json.dumps(result, ensure_ascii=False,
                                          indent=2, allow_nan=False).encode("utf-8"))
        atomic_write(out_html, page.encode("utf-8"))
        ttm = result["ttm_crosscheck"]
        projection, valuation = result.get("projection") or {}, result.get("scenario_valuation") or {}
        implied = result.get("implied_growth") or {}
        return {
            "ok": True, "company": result["company"], "ticker": ticker,
            "cik": result["cik"], "as_of": as_of, "mode": mode,
            "projection_status": projection.get("status"), "valuation_status": valuation.get("status"),
            "valuation_missing": valuation.get("missing", []),
            "implied_growth_status": implied.get("status"), "implied_growth": implied.get("implied_growth"),
            "source": source, "coverage_status": result["coverage_status"],
            "annual_end": result["annual_source_audit"].get("latest_any_fy_end"),
            "ttm_end": ttm.get("primary", {}).get("periods", {}).get("current_9m_end"),
            "ttm_status": ttm["status"], "sector": sector,
            "research_gaps": result["research_gaps"],
            "report_url": "/" + out_html.relative_to(self.root).as_posix(),
            "no_investment_advice": True,
        }


class Website(SimpleHTTPRequestHandler):
    def __init__(self, *args, service, **kwargs):
        self.service = service
        super().__init__(*args, directory=str(service.root), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        super().end_headers()

    def respond(self, status, data):
        blob = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def _safe_file(self):
        path = unquote(urlsplit(self.path).path)
        if path in ("/", "/index.html", "/favicon.ico"):
            return True
        if not path.startswith("/reports/"):
            return False
        resolved = Path(self.translate_path(path)).resolve()
        base = (self.service.root / "reports").resolve()
        if not resolved.is_relative_to(base):
            return False
        if resolved.is_dir():
            return path.endswith("/")
        return resolved.is_file() and resolved.suffix.lower() in (".html", ".htm")

    def do_GET(self):
        if self.path == "/api/health":
            return self.respond(200, {"version": VERSION, "api_available": True,
                                      "online_configured": bool(EMAIL_RE.search(self.service.user_agent or "")),
                                      "modes": MODES})
        if not self._safe_file():
            return self.send_error(404)
        if urlsplit(self.path).path == "/favicon.ico":
            self.send_response(204)
            return self.end_headers()
        return super().do_GET()

    def do_HEAD(self):
        if not self._safe_file():
            return self.send_error(404)
        return super().do_HEAD()

    def do_POST(self):
        if self.path not in ("/api/analyze", "/api/sec-scan"):
            return self.respond(404, {"ok": False, "error": "API yolu bulunamadı"})
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if origin:
            parts = urlsplit(origin)
            if parts.netloc.lower() != host.lower() or parts.scheme not in ("https", "http"):
                return self.respond(403, {"ok": False, "error": "Cross-origin POST engellendi"})
        if self.headers.get("Sec-Fetch-Site") in ("cross-site", "same-site"):
            return self.respond(403, {"ok": False, "error": "Cross-site POST engellendi"})
        key = self.headers.get("X-Invest-AI-Key", "")
        if not hmac.compare_digest(key, self.service.secret):
            return self.respond(403, {"ok": False, "error": "Erişim anahtarını terminalden alıp forma yaz."})
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            return self.respond(415, {"ok": False, "error": "JSON gerekli"})
        length = self.headers.get("Content-Length", "")
        if not length.isdigit() or not 0 < int(length) <= MAX_BODY_BYTES:
            return self.respond(413, {"ok": False, "error": "İstek boyutu geçersiz"})
        try:
            payload = json.loads(self.rfile.read(int(length)))
        except (ValueError, UnicodeError):
            return self.respond(400, {"ok": False, "error": "JSON okunamadı"})
        try:
            return self.respond(200, self.service.scan_sec_list(payload) if self.path == "/api/sec-scan" else self.service.analyze(payload))
        except RequestError as exc:
            return self.respond(exc.status, {"ok": False, "error": str(exc)})
        except (KeyError, OSError, TypeError, ValueError) as exc:
            self.log_error("Research engine error: %s", type(exc).__name__)
            return self.respond(422, {"ok": False, "error": "Kaynak veya finansal veri doğrulanamadı. Terminal kayıtlarını incele."})


def build_server(service, *, host="127.0.0.1", port=8000):
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError("Web development server must bind to loopback")
    if not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("invalid port")
    return ThreadingHTTPServer((host, port), partial(Website, service=service))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Private INVEST_AI web research")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    service = ResearchService()
    server = build_server(service, port=args.port)
    print(f"INVEST_AI {VERSION}: http://127.0.0.1:{server.server_port}", flush=True)
    print("WEB ANALİZ ANAHTARI (sitedeki parola kutusuna yapıştır): " + service.secret, flush=True)
    print("Codespaces Ports görünürlüğünü PRIVATE tut; Ctrl+C ile kapat.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
