"""Import center status uses the same authenticated local access boundary."""
from tests.test_auth_http import http


def test_center_requires_login_and_origin(http, tmp_path, monkeypatch):
    from selfos.sources.selection import save_sources
    from selfos.web.routes.auth import AuthRoutes
    from selfos.web.server import Handler
    monkeypatch.setattr(Handler, '_auth_guard', AuthRoutes._auth_guard)
    request, auth = http
    source = tmp_path / 'synthetic'
    source.mkdir()
    save_sources(tmp_path / 'app/vault', {'roots': [str(source)], 'exclusions': []})
    assert request('/__import_center__')[0] == 401
    auth.setup('synthetic center password')
    cookie = 'selfos_session=' + auth.login('synthetic center password')
    code, result, _ = request('/__import_center__', cookie=cookie)
    assert code == 200 and len(result['sources']) == 1
    assert request('/__import_center__?limit=51', cookie=cookie)[0] == 400
    assert request('/__import_center__?offset=-1', cookie=cookie)[0] == 400
