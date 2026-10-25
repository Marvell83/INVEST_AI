"""INVEST_AI static portal integration tests; offline and Python standard library."""
from __future__ import annotations

from functools import partial
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import unittest
import shutil
import subprocess
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"


class CheckMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = False
        self.title_text = ""
        self.sections = set()
        self.nav_targets = set()
        self.iframes = []
        self.links = []
        self.scripts = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "title":
            self.title = True
        if tag == "section" and "id" in attributes:
            self.sections.add(attributes["id"])
        if tag == "button" and "data-screen" in attributes:
            self.nav_targets.add(attributes["data-screen"])
        if tag == "iframe":
            self.iframes.append(attributes)
        if tag == "a" and "href" in attributes:
            self.links.append(attributes["href"])
        if tag == "script":
            self.scripts += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self.title = False

    def handle_data(self, data):
        if self.title:
            self.title_text += data


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class InvestAISiteTests(unittest.TestCase):
    def test_root_homepage_has_navigation_and_report_viewer(self):
        src = INDEX.read_text(encoding="utf-8")
        html = CheckMarkup()
        html.feed(src)
        self.assertIn("INVEST_AI", html.title_text)
        self.assertEqual(
            html.nav_targets,
            {"ana", "raporlar", "araclar", "hakkinda"})
        self.assertTrue({
            "screen-ana", "screen-raporlar", "screen-araclar",
            "screen-hakkinda", "screen-viewer",
        }.issubset(html.sections))
        self.assertEqual(html.scripts, 1)
        self.assertEqual(len(html.iframes), 1)
        self.assertIn("sandbox", html.iframes[0])
        self.assertIn("reports/", html.links)

    def test_report_discovery_is_dynamic_not_hardcoded(self):
        src = INDEX.read_text(encoding="utf-8")
        self.assertIn('new URL("reports/", document.baseURI)', src)
        self.assertIn("await fetch(directory.href", src)
        self.assertIn('querySelectorAll("a[href]")', src)
        self.assertIn("insideReports(dest)", src)
        self.assertIn('replaceChildren()', src)
        self.assertIn("textContent = item.name", src)
        self.assertIn("textContent = item.path", src)
        self.assertNotIn("eval(", src)
        self.assertNotIn("document.write(", src)

    def test_report_browser_separates_legacy_from_web_sources(self):
        src = INDEX.read_text(encoding="utf-8")
        # Existing 2026-10-21 Piotroski HTML stays in the legacy reports folder.
        self.assertTrue((ROOT / "reports/Apple_SEC_Piotroski_2026-10-21.html").is_file())
        self.assertIn('id="report-kind-filter"', src)
        self.assertIn('value="web">Web analizleri (v0.6)', src)
        self.assertIn('value="previous">Önceki / terminal raporları', src)
        self.assertIn('path.startsWith("reports/research/")', src)
        self.assertIn('kind:"previous"', src)
        self.assertIn('kind:"web"', src)
        self.assertIn("Örnek / manuel aktarım", src)
        self.assertIn("SEC üzerinden indirme", src)
        self.assertIn("Yerel SEC arşivi", src)
        self.assertIn("Bilgi kesme tarihi:", src)
        self.assertIn("Tarih tek başına verinin güncelliğini kanıtlamaz", src)
        self.assertIn('a.meta.kind === "web" ? -1 : 1', src)
        self.assertIn("kindFilter.addEventListener", src)

    def test_site_shows_web_version_and_new_reports_from_api(self):
        src = INDEX.read_text(encoding="utf-8")
        self.assertIn("Araştırma Merkezi · v0.6", src)
        self.assertIn('filename:data.report_url.split("/").pop()', src)
        self.assertIn("meta:reportMeta(data.report_url.slice(1)", src)
        self.assertIn('document.getElementById("viewer-provenance")', src)
        self.assertIn('document.createElement("span")', src)
        self.assertIn('heading.textContent = isError ?', src)


    def test_sec_company_scanner_has_live_button_and_paginated_results(self):
        src = INDEX.read_text(encoding="utf-8")
        for item in ('id="sec-scan-submit"', 'id="sec-scan-panel"',
                     'id="sec-scan-search"', 'id="sec-scan-rows"',
                     'id="sec-scan-prev"', 'id="sec-scan-next"',
                     '"/api/sec-scan"', 'SEC verilerini tara'):
            self.assertIn(item, src)
        self.assertIn('choose.textContent = "Seç"', src)
        self.assertIn('body: JSON.stringify({query:secScanQuery, offset, refresh})', src)


    def test_frontend_javascript_parses_when_node_available(self):
        if not shutil.which("node"):
            self.skipTest("Node.js is optional; JavaScript syntax check unavailable")
        src = INDEX.read_text(encoding="utf-8")
        script = src.split("<script>", 1)[1].split("</script>", 1)[0]
        result = subprocess.run(["node", "--check", "-"], input=script, text=True,
                                capture_output=True, check=False, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_financial_screener_excel_style_controls_exist(self):
        src = INDEX.read_text(encoding="utf-8")
        for control in ('fundamentals-open', 'fundamentals-panel', 'fundamentals-columns',
                        'fundamentals-filter-column', 'fundamentals-filter-min',
                        'fundamentals-filter-max', 'fundamentals-add-filter',
                        'fundamentals-decision', 'fundamentals-yield',
                        'fundamentals-csv', 'fundamentals-table',
                        'fundamentals-coverage'):
            self.assertIn(f'id="{control}"', src)
        self.assertIn('"/api/screener"', src)
        self.assertIn('filteredFundamentals()', src)
        self.assertIn('sort.textContent = label', src)
        self.assertIn('CSV indir', src)

    def test_bulk_sec_download_button_and_status_polling(self):
        page = INDEX.read_text(encoding="utf-8")
        for word in ('id="sec-bulk-start"', 'id="sec-bulk-status"',
                     '"/api/bulk/start"', '"/api/bulk/status"',
                     'Tüm SEC finansallarını indir ve tara'):
            self.assertIn(word, page)

    def test_demo_command_has_existing_source_and_modules(self):
        src = INDEX.read_text(encoding="utf-8")
        for required in (
            "sirket_arastirma_akisi.py",
            "sec_finansal_degisim.py",
            "sec_degisim_raporu.py",
            "apple_ttm_evidence_2026-10-21.json",
            "reports/apple_arastirma.html",
        ):
            self.assertIn(required, src)
        self.assertTrue((ROOT / "sirket_arastirma_akisi.py").is_file())
        self.assertTrue((ROOT / "ornekler/apple_ttm_evidence_2026-10-21.json").is_file())

    def test_python_http_server_automatically_serves_homepage(self):
        handler = partial(QuietHandler, directory=str(ROOT))
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        try:
            base = "http://127.0.0.1:" + str(httpd.server_port)
            with urlopen(base + "/", timeout=3) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(b"INVEST_AI |", response.read(1000))
            with urlopen(base + "/reports/", timeout=3) as response:
                self.assertEqual(response.status, 200)
                content = response.read()
                self.assertIn(b"<html", content.lower())
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
