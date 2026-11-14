"""Knowledge questions are private, bounded authenticated actions."""
from email.message import Message
from io import BytesIO
from types import SimpleNamespace

import pytest
from tests.test_auth_http import http
from tests.test_knowledge_qa_service import qa_vault, grounded


def test_qa_requires_login_and_empty_vault_never_calls_provider(http, monkeypatch):
    request, auth = http
    assert request('/__knowledge_qa_context__')[0] == 401
    assert request('/__knowledge_qa_citation__?record=x&revision=x')[0] == 401
    assert request('/__knowledge_qa__', {'question': 'What am I doing?'})[0] == 401
    auth.setup('synthetic knowledge password')
    cookie = 'selfos_session=' + auth.login('synthetic knowledge password')
    monkeypatch.setattr('selfos.providers.client.request_opener', lambda *a, **k: pytest.fail('Empty vault calls model'))
    assert request('/__knowledge_qa_context__', cookie=cookie)[:2] == (200, {'projects': []})
    code, data, _ = request('/__knowledge_qa__', {'question': 'What am I doing?'}, cookie)
    assert code == 200 and data['status'] == 'insufficient_evidence'
    for body in ({}, {'question': ''}, {'question': 'x' * 2001}, {'question': 'Hello', 'unknown': 1},
                 {'question': 'Hello', 'project': 1}, {'question': 'Hello', 'locale': 'unknown'}):
        assert request('/__knowledge_qa__', body, cookie)[0] == 400


@pytest.mark.parametrize('headers', [[], [('Content-Length', '0')], [('Content-Length', '65537')],
    [('Content-Length', '2'), ('Content-Length', '2')], [('Content-Length', '2'), ('Transfer-Encoding', 'chunked')]])
def test_qa_bad_framing_rejected_before_read(headers):
    from selfos.web.routes.actions import ActionsRoutes
    instance = ActionsRoutes()
    instance.path = '/__knowledge_qa__'
    instance.headers = Message()
    for key, value in headers:
        instance.headers[key] = value
    instance._local_request = lambda: True
    instance._auth_guard = lambda: True
    instance._send_json = lambda code, data: (code, data)
    instance._read_body = lambda: pytest.fail('Invalid framing read body')
    assert instance.do_POST()[0] == 400


def test_qa_expired_session_cannot_return_private_answer(http, monkeypatch):
    request, auth = http
    auth.setup('synthetic knowledge password')
    token = auth.login('synthetic knowledge password')
    cookie = 'selfos_session=' + token
    def answer(*args, cancel, **kwargs):
        auth.logout(token)
        from selfos.app.knowledge_qa import KnowledgeQAError
        assert cancel()
        raise KnowledgeQAError('cancelled')
    monkeypatch.setattr('selfos.app.knowledge_qa.answer_question', answer)
    assert request('/__knowledge_qa__', {'question': 'What am I doing?'}, cookie)[0] == 409


def test_source_result_is_revalidated_before_return(http, qa_vault, monkeypatch):
    import json
    import selfos.web.server as runtime
    from selfos.app.knowledge_qa import answer_question
    request, auth = http;vault, _ = qa_vault
    monkeypatch.setattr(runtime, 'VAULT', vault)
    auth.setup('synthetic knowledge password')
    cookie = 'selfos_session=' + auth.login('synthetic knowledge password')
    citation = answer_question(vault, vault.parent, 'Why SQLite?', answerer=grounded)['references'][0]
    def change_while_reading(*args, **kwargs):
        path = vault / '.knowledge_pipeline.json'
        state = json.loads(path.read_text(encoding='utf-8'))
        state['cards']['alpha']['intent'] = 'Changed during source read'
        path.write_text(json.dumps(state), encoding='utf-8')
        return {'text': 'MUST NOT LEAK CHANGED SOURCE'}
    monkeypatch.setattr('selfos.app.library.knowledge_source', change_while_reading)
    code, data, _ = request('/__knowledge_source__?id=m1&qa_record=' + citation['id'] + '&qa_revision=' + citation['revision'], cookie=cookie)
    assert code == 400 and data['code'] == 'knowledge_changed'
    assert 'MUST NOT LEAK' not in str(data)
