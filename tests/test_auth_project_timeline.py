import json
import pytest
from tests.test_project_timeline import fixture
from tests.test_auth_http import http
from selfos.app.library import list_knowledge


def save(path, state=None):
    path.mkdir(parents=True, exist_ok=True)
    (path / ".knowledge_pipeline.json").write_text(json.dumps(state or fixture()), encoding="utf-8")
    return list_knowledge(path, "projects")["items"][0]["id"]


def test_timeline_filters_pagination_and_missing_sources_are_consistent(tmp_path):
    from selfos.app.library import knowledge_timeline
    state = fixture()
    del state["sources"]["a"]
    identity = save(tmp_path, state)
    result = knowledge_timeline(tmp_path, identity, category="goals", limit=1)
    assert result["current"]["status"] == "completed"
    assert result["total"] >= 2 and len(result["items"]) == 1
    assert result["items"][0]["type"] == "goals"
    assert result["items"][0]["unavailable_source_count"] == 1
    later = knowledge_timeline(tmp_path, identity, category="goals", offset=1, limit=1)
    assert later["items"][0]["id"] != result["items"][0]["id"]
    assert "path" not in str(result) and "alpha" not in result["project_id"]


def test_timeline_reloads_canonical_edits_and_rejects_invalid_requests(tmp_path):
    from selfos.app.library import knowledge_timeline
    state = fixture()
    identity = save(tmp_path, state)
    before = (tmp_path / ".knowledge_pipeline.json").read_bytes()
    assert knowledge_timeline(tmp_path, identity)["current"]["status"] == "completed"
    assert (tmp_path / ".knowledge_pipeline.json").read_bytes() == before
    state["cards"]["alpha"]["status"] = "paused"
    identity = save(tmp_path, state)
    assert knowledge_timeline(tmp_path, identity)["current"]["status"] == "paused"
    for kwargs in [{"category": "bad"}, {"offset": -1}, {"offset": True}, {"limit": 0}, {"limit": True}]:
        with pytest.raises(ValueError):
            knowledge_timeline(tmp_path, identity, **kwargs)
    with pytest.raises(KeyError):
        knowledge_timeline(tmp_path, "missing")


def test_timeline_route_requires_login_and_returns_project_after_login(http):
    request, auth = http
    identity = save(auth.vault)
    assert request("/__knowledge_timeline__?id=" + identity)[0] == 401
    auth.reset("a sufficiently long password")
    cookie = "selfos_session=" + auth.login("a sufficiently long password")
    code, data, _ = request("/__knowledge_timeline__?id=" + identity, cookie=cookie)
    assert code == 200 and data["current"]["status"] == "completed"
    assert request("/__knowledge_timeline__?id=missing", cookie=cookie)[0] == 404
    assert request("/__knowledge_timeline__?id=" + identity + "&offset=bad", cookie=cookie)[0] == 400


def test_timeline_lookup_does_not_rebuild_unrelated_history(tmp_path, monkeypatch):
    import selfos.app.library as library
    identity = save(tmp_path)
    def forbidden(*args):
        raise AssertionError("Timeline lookup must not project unrelated history")
    monkeypatch.setattr(library, '_history', forbidden)
    monkeypatch.setattr(library, 'extract_conversations', forbidden)
    assert library.knowledge_timeline(tmp_path, identity)['items']


def test_changed_history_between_pages_restarts_projection_explicitly(tmp_path):
    from selfos.app.library import knowledge_timeline
    state = fixture()
    identity = save(tmp_path, state)
    first = knowledge_timeline(tmp_path, identity, category='goals', limit=1)
    older = {**state['summaries']['a']['project'], 'intent': 'Earlier goal', 'updated_at': '2025-12-01', 'source_ids': ['old']}
    state['summaries']['older'] = {'project': older}
    save(tmp_path, state)
    second = knowledge_timeline(tmp_path, identity, category='goals', offset=1, limit=1, revision=first['revision'])
    assert second['reset_required'] and second['offset'] == 0
    assert second['revision'] != first['revision']
    assert second['items'][0]['text'] == 'Earlier goal'


def test_timeline_rejects_cross_site_requests_with_an_authenticated_cookie(tmp_path, monkeypatch):
    import threading
    from http.server import ThreadingHTTPServer
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
    import selfos.web.server as runtime
    from selfos.security.auth import AuthManager
    root = tmp_path / 'app'
    vault = root / 'vault'
    identity = save(vault)
    monkeypatch.setattr(runtime, 'ROOT', root)
    monkeypatch.setattr(runtime, 'VAULT', vault)
    server = ThreadingHTTPServer(('127.0.0.1', 0), runtime.Handler)
    server.auth = AuthManager(root, vault, directory=tmp_path / 'private')
    server.auth.reset('a sufficiently long password')
    cookie = 'selfos_session=' + server.auth.login('a sufficiently long password')
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for headers in [{'Origin': 'https://outside.example'}, {'Sec-Fetch-Site': 'cross-site'}]:
            request = Request('http://127.0.0.1:' + str(server.server_port) + '/__knowledge_timeline__?id=' + identity,
                              headers={**headers, 'Cookie': cookie})
            with pytest.raises(HTTPError) as error:
                urlopen(request)
            assert error.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
