"""Synthetic UI checks for explicit preview, preserved drafts and unknown cost."""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import pytest
from selfos.web.i18n import runtime
from selfos.web.rendering.resources import frontend_text


def test_preview_budget_and_locale_switch_preserve_inputs(tmp_path):
    playwright = pytest.importorskip('playwright.sync_api')
    chrome = Path(os.environ.get('SELFOS_CHROME', 'C:/Users/I748319/.cache/puppeteer/chrome/win64-135.0.7049.95/chrome-win64/chrome.exe'))
    if not chrome.exists(): pytest.skip('Synthetic Chromium is unavailable')
    budget = dict(max_requests=100, input_price=None, output_price=None, pricing_known=False)
    status = dict(settings=dict(domains=['work'], detail='balanced'), counts={}, last_operation=None, needs_rebuild=False,
        usage=dict(budget=budget, runs=[], diagnostics=0, bounded=False))
    preview = dict(files_scanned=2, messages_scanned=30, compact_parts=5, pending_parts=2, cached_parts=3, projects=1,
        bounded=True, warnings=['file_limit'], budget=budget, estimate=dict(calls=dict(low=2, high=10),
        input_tokens=dict(low=100, high=2000), output_tokens=dict(low=0, high=8000), cost_usd=None))
    html = ('<html><head><meta name="viewport" content="width=device-width, initial-scale=1">'+runtime()+
        '</head><body>'+frontend_text('templates/import-controls.html')+'</body></html>').encode()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.end_headers(); self.wfile.write(html)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    calls = []
    def route(request):
        url = request.request.url
        calls.append(url)
        result = preview if url.endswith('/__knowledge_workload__') else status
        if url.endswith('/__knowledge_budget__'):
            patch = request.request.post_data_json
            assert patch == dict(max_requests=7, input_price=None, output_price=None)
            result = {**budget, **patch}
        request.fulfill(status=200, content_type='application/json', body=json.dumps(result))
    try:
        with playwright.sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(chrome), headless=True)
            page = browser.new_page(viewport=dict(width=1280, height=900))
            page.route('**/__knowledge*', route)
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.evaluate('window.selfosI18n.setLocale("en"); openKnowledgeSettings()')
            page.wait_for_function('document.getElementById("workload-limit")?.value === "100"')
            assert not any(url.endswith('/__knowledge_workload__') for url in calls)
            page.locator('#workload-preview').click()
            page.wait_for_function('document.getElementById("workload-preview-result").textContent.includes("2 pending")')
            assert 'Cost unknown' in page.locator('#workload-preview-result').inner_text()
            page.locator('#workload-limit').fill('7')
            page.evaluate('window.selfosI18n.setLocale("zh-CN")')
            assert page.locator('#workload-limit').input_value() == '7'
            page.locator('#workload-save').click()
            page.wait_for_function('document.getElementById("workload-status").textContent === window.selfosI18n.t("workload.saved")')
            assert sum(url.endswith('/__knowledge_workload__') for url in calls) == 1
            page.evaluate('window.selfosI18n.setLocale("en")')
            assert 'saved' in page.locator('#workload-status').inner_text().lower()
            page.screenshot(path=str(tmp_path / 'workload-en-1280.png'))
            page.set_viewport_size(dict(width=390, height=844))
            page.evaluate('window.selfosI18n.setLocale("zh-CN")')
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.screenshot(path=str(tmp_path / 'workload-zh-390.png'))
            browser.close()
    finally:
        server.shutdown(); server.server_close()
