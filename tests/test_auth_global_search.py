import json

from tests.test_auth_http import http
from tests.test_document_sources import registered


def test_global_filters_require_authentication_and_do_not_scan_sources(http, tmp_path, monkeypatch):
    request, auth = http
    auth.setup('synthetic global search password')
    cookie = 'selfos_session=' + auth.login('synthetic global search password')
    vault = tmp_path / 'app' / 'vault'
    vault.mkdir(parents=True, exist_ok=True)
    state = {'cards': {}, 'preferences': [{'key': 'style', 'value': 'concise',
        'text': 'Prefer concise updates', 'kind': 'user_fact', 'source_ids': ['m1']}],
        'sources': {'m1': {'source': 'codex', 'role': 'user', 'timestamp': '2026-11-10T08:00:00Z'}}}
    (vault / '.knowledge_pipeline.json').write_text(json.dumps(state), encoding='utf-8')
    def forbid(*args, **kwargs):
        raise AssertionError('Search must not scan sources')
    monkeypatch.setattr('selfos.app.library.extract_conversations', forbid)
    assert request('/__knowledge__?query=concise')[0] == 401
    code, data, _ = request('/__knowledge__?source=claude', cookie=cookie)
    assert code == 200 and data['total'] == 0
    code, data, _ = request('/__knowledge__?category=all&source=codex&date_from=2026-11-10&date_to=2026-11-10', cookie=cookie)
    assert code == 200 and data['total'] == 1
    assert data['items'][0]['category'] == 'preferences'
    assert request('/__knowledge__?date_from=invalid', cookie=cookie)[0] == 400


def test_registered_source_http_pages_and_localized_error_codes(http, registered, monkeypatch):
    import selfos.web.server as server
    request, auth = http
    auth.setup('synthetic document source password')
    cookie = 'selfos_session=' + auth.login('synthetic document source password')
    vault, path, _ = registered
    monkeypatch.setattr(server, 'VAULT', vault)
    code, data, _ = request('/__knowledge_source__?id=upload1&offset=15&limit=12', cookie=cookie)
    assert code == 200 and data['text'] == '\nAtomic inst'
    assert data['next_offset'] == 27
    path.write_bytes(b'Changed source')
    code, data, _ = request('/__knowledge_source__?id=upload1', cookie=cookie)
    assert code == 400 and data['code'] == 'source_changed'


def test_cached_dashboard_get_refreshes_search_without_rewriting_file(http, tmp_path, monkeypatch):
    import selfos.web.server as server
    request, auth = http
    auth.setup('synthetic cached dashboard password')
    cookie = 'selfos_session=' + auth.login('synthetic cached dashboard password')
    page = tmp_path / 'dashboard.html'
    old = '<html><head><style>.knowledge-library{color:red}</style></head><body>'
    old += '<section id="knowledge-library">legacy</section><dialog id="kb-detail"></dialog><script>window.browseKnowledge=function(){};</script>'
    old += '<main>Existing scores remain</main></body></html>'
    page.write_text(old, encoding='utf-8')
    raw = page.read_bytes()
    monkeypatch.setattr(server, 'DASHBOARD', page)
    code, body, _ = request('/', cookie=cookie)
    assert code == 200 and 'id="kb-project"' in body
    assert 'Existing scores remain' in body and 'legacySearch' not in body
    assert page.read_bytes() == raw
