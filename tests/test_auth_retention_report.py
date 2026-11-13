from tests.test_auth_http import http


def test_quality_route_requires_login_and_is_read_only(http, monkeypatch):
    request, auth = http
    assert request('/__knowledge_quality__')[0] == 401
    auth.setup('a sufficiently long password')
    cookie='selfos_session='+auth.login('a sufficiently long password')
    import selfos.sources.conversations as conversations
    def forbidden(*args, **kwargs): raise AssertionError('Report must not discover sources')
    monkeypatch.setattr(conversations,'local_roots',forbidden)
    monkeypatch.setattr(conversations,'extract_conversations',forbidden)
    code,data,_=request('/__knowledge_quality__',cookie=cookie)
    assert code == 200
    assert data['canonical'] is True
    assert data['categories']['preferences']['explanation'] == 'unknown'
