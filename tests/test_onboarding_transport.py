"""Transport attempts, including failed HTTP requests, share the sample allowance."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request

import pytest


@pytest.mark.parametrize("provider_factory", ["raw", "summarizer", "refiner"])
def test_failed_http_attempts_consume_budget_and_exhaustion_never_sends(tmp_path, provider_factory):
    from selfos.app.onboarding import build_preview
    from selfos.sources.selection import save_sources
    from selfos.storage.onboarding import SampleBudget, ModelBudgetExceeded
    from selfos.providers.client import request_opener
    from selfos.providers.settings import save_config
    requests = []
    class Model(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(503)
            self.end_headers()
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Model)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = tmp_path / "source"
    root.mkdir()
    vault = tmp_path / "vault"
    save_sources(vault, {"roots": [str(root)], "exclusions": []})
    preview = build_preview(vault)
    save_config(tmp_path, {"provider": "openai", "model": "synthetic-test-model",
                          "base_url": f"http://127.0.0.1:{server.server_port}/v1", "proxy_mode": "direct"})
    body = {"max_tokens": 20, "messages": [{"role": "user", "content": "synthetic request"}]}
    request = Request("http://127.0.0.1", data=json.dumps(body).encode())
    def attempt():
        budget = SampleBudget(vault, preview["id"])
        if provider_factory == "raw":
            return request_opener(tmp_path, budget=budget)(request)
        from selfos.providers.knowledge import api_summarizer, api_refiner
        if provider_factory == "summarizer":
            return api_summarizer(tmp_path, budget=budget)({"project_id": "test-project", "messages": [
                {"id": "synthetic-message", "role": "user", "text": "I prefer maintainable Python and explicit failure recovery.", "timestamp": "2026-11-13"}]})
        return api_refiner(tmp_path, budget=budget)({"project": {"project_id": "test-project", "source_ids": ["synthetic-message"]},
            "lessons": [], "sources": {"synthetic-message": {"role": "user", "timestamp": "2026-11-13"}},
            "user_corrections": {"project": {"title": "Manually corrected purpose", "intent": "Respect the user correction",
                "original_records": [{"text": "PRIVATE RAW ORIGINAL"}]}, "lessons": []}})
    try:
        for _ in range(12):
            # A fresh opener represents a new process/provider/retry, same persisted quota.
            with pytest.raises(RuntimeError, match="HTTP 503"):
                attempt()
        with pytest.raises(ModelBudgetExceeded):
            attempt()
        assert len(requests) == 12
        assert SampleBudget(vault, preview["id"]).status()["remaining"] == 0
        if provider_factory == "refiner":
            assert b"Manually corrected purpose" in requests[0]
            assert b"PRIVATE RAW ORIGINAL" not in requests[0]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
