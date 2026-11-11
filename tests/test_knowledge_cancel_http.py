import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
import serve


def test_stop_endpoint_signals_running_import_and_idle_is_harmless(tmp_path, monkeypatch):
    monkeypatch.setattr(serve, "KNOWLEDGE_RUN", {"stop_file": None})
    server = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def stop():
            req = Request(f"http://127.0.0.1:{server.server_port}/__knowledge_stop__", data=b"{}", method="POST")
            with urlopen(req) as response:
                return json.loads(response.read())
        assert stop()["running"] is False
        marker = tmp_path / "stop"
        serve.KNOWLEDGE_RUN["stop_file"] = marker
        assert stop()["running"] is True
        assert marker.exists()
    finally:
        server.shutdown()
        server.server_close()


def test_chat_context_includes_project_summaries_and_lessons(tmp_path, monkeypatch):
    monkeypatch.setattr(serve, "VAULT", tmp_path)
    projects = tmp_path / "02_Work/projects"
    projects.mkdir(parents=True)
    (projects / "alpha.md").write_text("Alpha blocked by quota", encoding="utf-8")
    (tmp_path / "05_Life").mkdir()
    (tmp_path / "05_Life/lessons.md").write_text("Use bounded retries", encoding="utf-8")
    text = serve._load_vault_context()
    assert "Alpha blocked by quota" in text
    assert "Use bounded retries" in text
