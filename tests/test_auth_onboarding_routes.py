"""Setup endpoints require login and cannot mutate an active import."""
from tests.test_auth_http import http
import pytest


def test_onboarding_requires_login_and_read_is_side_effect_free(http, tmp_path, monkeypatch):
    import selfos.sources.selection as sources
    root = tmp_path / 'source'
    root.mkdir()
    monkeypatch.setattr(sources, 'local_roots', lambda: [root])
    request, auth = http
    assert request('/__onboarding__')[0] == 401
    assert request('/__onboarding__', {'action': 'skip'})[0] == 401
    auth.setup('synthetic onboarding password')
    cookie = 'selfos_session=' + auth.login('synthetic onboarding password')
    code, result, _ = request('/__onboarding__', cookie=cookie)
    assert code == 200
    assert result['progress']['status'] == 'new'
    assert not (tmp_path / 'app/vault/.knowledge_onboarding.json').exists()
    assert request('/__onboarding__', {'action': 'skip'}, cookie)[1]['progress']['status'] == 'skipped'


def test_active_import_rejects_setup_mutation(http, tmp_path, monkeypatch):
    import selfos.web.server as server
    request, auth = http
    auth.setup('synthetic onboarding password')
    cookie = 'selfos_session=' + auth.login('synthetic onboarding password')
    monkeypatch.setitem(server.KNOWLEDGE_RUN, 'stop_file', tmp_path / 'stop')
    assert request('/__onboarding__', {'action': 'preview'}, cookie)[0] == 409
    assert not (tmp_path / 'app/vault/.knowledge_onboarding.json').exists()


@pytest.mark.parametrize('query', ['preview=invalid', 'preview=', 'preview=invalid&preview=other'])
def test_invalid_stream_preview_never_spawns_default_import(http, tmp_path, monkeypatch, query):
    import selfos.web.server as server
    request, auth = http
    auth.setup('synthetic onboarding password')
    cookie = 'selfos_session=' + auth.login('synthetic onboarding password')
    def forbidden(*args, **kwargs):
        raise AssertionError('must not start subprocess')
    monkeypatch.setattr(server.subprocess, 'Popen', forbidden)
    assert request('/__knowledge_stream__?' + query, cookie=cookie)[0] == 400
