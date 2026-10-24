"""INVEST_AI v0.2: authenticated local web research (Python stdlib only).

A local browser POST executes existing SEC/TTM/Piotroski engines. Requires a
session API key printed in the terminal, no user-facing shell input, no trading.
SEC requests are serialised/throttled and archived with a content hash.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import threading
import urllib.error
from urllib.parse import unquote, urlsplit

from sec_companyfacts import download_companyfacts
from sec_toplu_tarama import (
    SECThrottle, StopSECRequests, _atomic_write, _cached, _canonical_bytes,
    _check_doc, _load_json, _mapping, _save_capture, download_ticker_map,
)
from sirket_arastirma_akisi import build_company_research, render_company_research

ROOT = Path(__file__).resolve().parent
VERSION = "invest-ai-web-0.2.0"
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")
EMAIL_RE = re.compile(r"\S+@\S+\.\S+")
MODES = ("demo", "live", "cache")
SECTORS = ("non_financial", "financial", "unknown")


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
            return _mapping(_load_json(path, max_bytes=12_000_000)), "SAVED_SEC_MAP"
        if path.is_file():
            age_seconds = self.clock().timestamp() - path.stat().st_mtime
            if mode == "live" and 0 <= age_seconds < 24 * 3600:
                return _mapping(_load_json(path, max_bytes=12_000_000)), "CACHED_SEC_MAP"
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
        table = _mapping(source)
        _atomic_write(path, _canonical_bytes(source))
        return table, "DOWNLOADED_SEC_MAP"

    def analyze(self, request):
        if not isinstance(request, dict) or set(request) != {"ticker", "mode", "sector"}:
            raise RequestError("ticker, mode ve sector alanları gerekir.")
        ticker, mode, sector = request["ticker"], request["mode"], request["sector"]
        if not isinstance(ticker, str):
            raise RequestError("Hisse sembolü metin olmalı.")
        ticker = ticker.strip().upper()
        if not TICKER_RE.fullmatch(ticker) or mode not in MODES or sector not in SECTORS:
            raise RequestError("Ticker, veri türü veya sektör geçersiz.")
        if not self.lock.acquire(blocking=False):
            raise RequestError("Bir analiz çalışıyor. Bittikten sonra yeniden dene.", 409)
        try:
            return self._run(ticker, mode, sector)
        finally:
            self.lock.release()

    def _run(self, ticker, mode, sector):
        if mode == "demo":
            if ticker != "AAPL":
                raise RequestError("Örnek veri yalnız AAPL içindir. Başka şirket için Güncel SEC seç.")
            cik = 320193
            as_of = "2026-10-21"
            raw = _load_json(self.root / "ornekler/apple_ttm_evidence_2026-10-21.json")
            _check_doc(raw, cik)
            source = "MANUAL_APPLE_EXAMPLE_NOT_LIVE_SEC"
            archive = None
            mapping_source = "EXAMPLE_FIXED_CIK"
        else:
            ticker_map, mapping_source = self._ticker_map(mode)
            if ticker not in ticker_map:
                raise RequestError("SEC ticker listesinde şirket bulunamadı: " + ticker, 404)
            cik = ticker_map[ticker]
            if mode == "cache":
                cached = _cached(self.root / "veri/sec_kaynaklari", f"{cik:010d}")
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
                _check_doc(raw, cik)
                _, _, archive = _save_capture(self.root / "veri/sec_kaynaklari",
                                              f"{cik:010d}", raw, self.clock())
                source = "SEC_DIRECT_DOWNLOAD_UNVERIFIED_INDEPENDENTLY"
            as_of = self.clock().date().isoformat()

        result = build_company_research(raw, expected_cik=cik, as_of=as_of,
                                        sector=sector,
                                        input_mode="sec_direct_download" if mode == "live" else "offline_file")
        result["source"]["web_data_mode"] = mode
        result["source"]["web_source_label"] = source
        result["source"]["ticker_map_provenance"] = mapping_source
        result["source"]["archive_path"] = archive.relative_to(self.root).as_posix() if archive else None
        page = render_company_research(result)
        digest = result["source"]["canonical_json_sha256"][:12]
        # A different analyst sector assumption must not overwrite an earlier report
        # generated from the same SEC snapshot with another classification.
        basename = f"{ticker}_{mode.upper()}_{as_of}_{sector}_{digest}"
        folder = self.root / "reports" / "research"
        out_json = folder / (basename + ".json")
        out_html = folder / (basename + ".html")
        _atomic_write(out_json, json.dumps(result, ensure_ascii=False,
                                           indent=2, allow_nan=False).encode("utf-8"))
        _atomic_write(out_html, page.encode("utf-8"))
        p = result["quality"]["piotroski"]
        ttm = result["ttm_crosscheck"]
        reasons = p.get("missing_reasons", {})
        annual_history_missing = (
            p.get("known_count") == 0 and len(reasons) == 9
            and set(reasons.values()) == {"TWO_COMPARABLE_ANNUAL_INCOME_PERIODS_REQUIRED"}
        )
        return {
            "ok": True, "company": result["company"], "ticker": ticker,
            "cik": result["cik"], "as_of": as_of, "mode": mode,
            "source": source, "coverage_status": result["coverage_status"],
            "annual_end": result["annual_source_audit"].get("latest_any_fy_end"),
            "ttm_end": ttm.get("primary", {}).get("periods", {}).get("current_9m_end"),
            "ttm_status": ttm["status"], "piotroski_score": p["score"],
            "piotroski_status": p["status"], "sector": sector,
            "piotroski_known_count": p["known_count"],
            "piotroski_missing_annual_history": annual_history_missing,
            "piotroski_range": p["score_range"], "research_gaps": result["research_gaps"],
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
        if self.path != "/api/analyze":
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
        if not length.isdigit() or not 0 < int(length) <= 512:
            return self.respond(413, {"ok": False, "error": "İstek boyutu geçersiz"})
        try:
            payload = json.loads(self.rfile.read(int(length)))
        except (ValueError, UnicodeError):
            return self.respond(400, {"ok": False, "error": "JSON okunamadı"})
        try:
            return self.respond(200, self.service.analyze(payload))
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
    print(f"INVEST_AI v0.2: http://127.0.0.1:{server.server_port}", flush=True)
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
