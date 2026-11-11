from tests.test_auth_http import http


def test_frontend_refactor_does_not_add_a_local_file_serving_route(http):
    request, auth = http
    auth.vault.mkdir(parents=True, exist_ok=True)
    (auth.vault / 'PROFILE.md').write_text('PRIVATE FRONTEND BOUNDARY FIXTURE', encoding='utf-8')
    auth.reset('synthetic frontend boundary password')
    cookie = 'selfos_session=' + auth.login('synthetic frontend boundary password')
    status, page, _ = request('/login')
    assert status == 200 and 'SelfOS' in page
    assert 'PRIVATE FRONTEND BOUNDARY FIXTURE' not in page
    for path in ['/vault/PROFILE.md', '/.env', '/static/../vault/PROFILE.md', '/__frontend_asset__?path=../vault/PROFILE.md', '/resources/web/manifest.json']:
        assert request(path)[0] == 401
        status, data, _ = request(path, cookie=cookie)
        assert status == 404
        assert 'PRIVATE FRONTEND BOUNDARY FIXTURE' not in str(data)
