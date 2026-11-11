import json
import io
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import pytest
import serve
from selfos.app.knowledge import run_knowledge
from tests.test_knowledge_service import source, summarize, refine


@pytest.fixture
def http(tmp_path, monkeypatch):
    monkeypatch.setattr(serve, 'VAULT', tmp_path / 'vault')
    monkeypatch.setattr(serve, 'KNOWLEDGE_RUN', {'stop_file': None})
    server = ThreadingHTTPServer(('127.0.0.1', 0), serve.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    def request(path, body=None):
        req = Request(f'http://127.0.0.1:{server.server_port}' + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Content-Type': 'application/json'})
        try:
            response = urlopen(req)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())
    yield request
    server.shutdown(); server.server_close()


def test_http_settings_round_trip_and_rejects_running_changes(http, tmp_path):
    assert http('/__knowledge_settings__')[1]['settings']['detail'] == 'balanced'
    code, data = http('/__knowledge_settings__', {'domains': ['research'], 'detail': 'concise'})
    assert code == 200 and data['settings']['domains'] == ['research']
    assert http('/__knowledge_settings__', {'domains': []})[0] == 400
    serve.KNOWLEDGE_RUN['stop_file'] = tmp_path / 'stop'
    assert http('/__knowledge_settings__', {'detail': 'detailed'})[0] == 409


def test_http_undo_and_stale_operation(http, tmp_path):
    roots, _ = source(tmp_path)
    result = run_knowledge(serve.VAULT, roots=[roots], summarize=summarize, refine=refine)
    assert http('/__knowledge_restore__', {'operation_id': 'stale'})[0] == 400
    assert http('/__knowledge_restore__', {'operation_id': result['operation_id']})[0] == 200
    assert http('/__knowledge_restore__', {'operation_id': result['operation_id']})[0] == 400


def test_context_includes_typed_records_without_source_hashes(tmp_path, monkeypatch):
    monkeypatch.setattr(serve, 'VAULT', tmp_path)
    (tmp_path / '.knowledge_pipeline.json').write_text(json.dumps({'cards': {},
        'personal_facts': [{'text': 'Works at Example', 'conflict': True, 'source_ids': ['secret-source-hash']}],
        'preferences': [{'text': 'Prefers short explanations'}]}))
    context = serve._load_vault_context()
    assert 'Works at Example' in context and 'Prefers short explanations' in context
    assert 'secret-source-hash' not in context and 'true' in context


def test_rebuild_stream_dispatches_cli_without_running_import(tmp_path, monkeypatch):
    calls=[]
    class Process:
        stdout=io.StringIO('Synthetic rebuild completed\n')
        returncode=0
        def poll(self): return 0
    monkeypatch.setattr(serve.subprocess,'Popen',lambda cmd,**kwargs: calls.append(cmd) or Process())
    monkeypatch.setattr(serve,'KNOWLEDGE_RUN',{'stop_file':None})
    server=ThreadingHTTPServer(('127.0.0.1',0),serve.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with urlopen(f'http://127.0.0.1:{server.server_port}/__knowledge_stream__?action=rebuild') as response:
            stream=response.read().decode()
        assert '--rebuild' in calls[0] and '--stop-file' in calls[0]
        assert '"done": true' in stream and '"ok": true' in stream
        assert serve.KNOWLEDGE_RUN['stop_file'] is None
    finally:
        server.shutdown();server.server_close()
