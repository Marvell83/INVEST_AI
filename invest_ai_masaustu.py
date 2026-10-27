"""Windows-friendly launcher for the existing offline-first INVEST_AI web UI.

PyInstaller bundles source modules + small static assets. All SEC archives and
user reports live in a stable per-user directory outside the executable bundle.
The program listens on 127.0.0.1 only and retains the existing session key.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import urllib.request
import webbrowser

from invest_ai_web import ResearchService, build_server

APP_NAME = "INVEST_AI"
STATIC_FILES = (
    "index.html",
    "ornekler/apple_ttm_evidence_2026-10-21.json",
)
USER_AGENT_FILENAME = "SEC_USER_AGENT.txt"


def bundled_root():
    """Resources packed into the PyInstaller _internal dir; never persist here."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)).resolve()


def workspace_path(environ=None):
    """Windows data survives EXE replacement and is independent of working dir."""
    environ = environ if environ is not None else os.environ
    location = environ.get("LOCALAPPDATA")
    return (Path(location) / APP_NAME if location else
            Path.home() / APP_NAME).resolve()


def prepare_workspace(*, source=None, destination=None):
    source = Path(source or bundled_root()).resolve()
    destination = Path(destination or workspace_path()).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    # Only bundled static files are refreshed. NEVER copy over SEC ZIP, SQLite or reports.
    for relative in STATIC_FILES:
        src = source / relative
        if not src.is_file():
            raise FileNotFoundError("Program kaynak dosyası eksik: " + relative)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or src.read_bytes() != target.read_bytes():
            temporary = target.with_name(target.name + ".new")
            shutil.copyfile(src, temporary)
            temporary.replace(target)
    (destination / "veri").mkdir(exist_ok=True)
    (destination / "reports").mkdir(exist_ok=True)
    # User-supplied email stays private in LOCALAPPDATA, never bundled/GitHub.
    email_file = destination / USER_AGENT_FILENAME
    if not email_file.exists():
        email_file.write_text(
            "# SEC sitesinden yeni veri indirirken kendi gecerli e-posta adresini yaz.\n"
            "# Ornek bicim: SEC_USER_AGENT=INVEST_AI Research ad@kurum.gov.tr\n"
            "# Bu dosyayi GitHub'a yukleme. Mevcut verileri okumak icin gerekli degil.\n"
            "SEC_USER_AGENT=\n",
            encoding="utf-8",
        )
    return destination


def local_sec_contact(root, environ=None):
    environ = environ if environ is not None else os.environ
    if environ.get("SEC_USER_AGENT", "").strip():
        return environ["SEC_USER_AGENT"].strip()
    file = Path(root) / USER_AGENT_FILENAME
    if not file.is_file() or file.stat().st_size > 2048:
        return ""
    try:
        lines = file.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        return ""
    for line in lines:
        if line.strip().startswith("SEC_USER_AGENT="):
            return line.split("=", 1)[1].strip()[:240]
    return ""


def self_test(root, service):
    """Run the actual HTTP health route without reaching the internet."""
    with build_server(service, port=0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/api/health"
            with urllib.request.urlopen(url, timeout=8) as response:
                payload = json.load(response)
            if not payload.get("api_available"):
                raise RuntimeError("Local INVEST_AI HTTP health check failed")
            if not (Path(root) / "index.html").is_file():
                raise RuntimeError("Missing local index.html")
            print("INVEST_AI_WINDOWS_SELF_TEST_OK", json.dumps({
                "version": payload.get("version"), "data_path": str(root),
                "loopback": True,
            }, ensure_ascii=False), flush=True)
        finally:
            server.shutdown()
            thread.join(timeout=5)


def main(argv=None):
    parser = argparse.ArgumentParser(description="INVEST_AI Windows masaustu baslaticisi")
    parser.add_argument("--port", type=int, default=0,
                        help="Local-only port; default is automatically selected")
    parser.add_argument("--no-browser", action="store_true",
                        help="Do not automatically open the browser")
    parser.add_argument("--self-test", action="store_true",
                        help="Check static resources and local HTTP API, then exit")
    args = parser.parse_args(argv)
    data_root = prepare_workspace()
    contact = local_sec_contact(data_root)
    service = ResearchService(root=data_root, user_agent=contact)
    if args.self_test:
        self_test(data_root, service)
        return 0

    with build_server(service, port=args.port) as server:
        url = f"http://127.0.0.1:{server.server_port}/#araclar"
        print("=" * 64, flush=True)
        print("INVEST_AI — WINDOWS YEREL UYGULAMA", flush=True)
        print("Bilgisayardaki verilerin: " + str(data_root), flush=True)
        print("Adres: " + url, flush=True)
        print("WEB ANALIZ ANAHTARI: " + service.secret, flush=True)
        if not contact:
            print("Yeni SEC indirmesi icin SEC_USER_AGENT.txt dosyasini doldur.", flush=True)
        print("Bu pencereyi kapatinca program durur. Sadece kendi bilgisayarinda acik.", flush=True)
        print("=" * 64, flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
