import json
import pytest
from selfos.storage.usage import RequestUsage


def test_legacy_prices_are_ignored_and_new_prices_rejected(tmp_path):
    from selfos.app.budget import read_budget, save_budget
    vault = tmp_path / 'vault'
    vault.mkdir()
    (vault / '.knowledge_budget.json').write_text(json.dumps(dict(version=1, max_requests=7, input_price=2, output_price=3)))
    assert read_budget(vault, tmp_path) == {'max_requests': 7}
    with pytest.raises(ValueError):
        save_budget(vault, tmp_path, {'input_price': 1})
    assert save_budget(vault, tmp_path, {'max_requests': 8}) == {'max_requests': 8}
    assert json.loads((vault / '.knowledge_budget.json').read_text()) == dict(version=1, max_requests=8)


@pytest.mark.parametrize('provider, usage, expected', [
    ('anthropic', dict(input_tokens=12, output_tokens=7, cache_read_input_tokens=100, cache_creation_input_tokens=20), (132, 7, 100, 20)),
    ('openai', dict(prompt_tokens=120, completion_tokens=7, prompt_tokens_details={'cached_tokens': 100}), (120, 7, 100, 0)),
])
def test_cache_token_counts_keep_provider_semantics(tmp_path, provider, usage, expected):
    meter = RequestUsage(tmp_path, 'a' * 32, 10)
    ticket = meter.claim()
    meter.observe(ticket, {'usage': usage}, provider)
    status = meter.status()
    assert (status['input_tokens'], status['output_tokens'], status['cache_read_tokens'], status['cache_creation_tokens']) == expected
    assert status['total_tokens'] == expected[0] + expected[1]


def test_transport_identity_overrides_runtime_identity(tmp_path):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.request import Request
    from selfos.providers.settings import save_config
    from selfos.providers.client import request_opener
    from selfos.app.budget import model_identity
    from selfos.storage.usage import request_usage_scope
    received, release = threading.Event(), threading.Event()
    sent_models = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            sent_models.append(json.loads(self.rfile.read(int(self.headers['Content-Length'])))['model'])
            received.set()
            release.wait(5)
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps({'choices': [{'message': {'content': 'ok'}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 12, 'completion_tokens': 7}}).encode())
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        save_config(tmp_path, dict(provider='openai', model='old', base_url=f'http://127.0.0.1:{server.server_port}/v1', proxy_mode='direct'))
        old_identity = model_identity(tmp_path)
        opener = request_opener(tmp_path)
        save_config(tmp_path, dict(model='new'))
        meter = RequestUsage(tmp_path / 'vault', 'b' * 32, 10, model_identity=model_identity(tmp_path))
        def invoke():
            with request_usage_scope(meter):
                opener(Request('http://placeholder', data=json.dumps({'messages': [], 'max_tokens': 10}).encode()))
        with ThreadPoolExecutor(max_workers=1) as workers:
            future = workers.submit(invoke)
            assert received.wait(5)
            pending = meter.status()
            assert pending['used'] == 1 and pending['missing_usage'] == 1
            release.set()
            future.result(timeout=5)
        assert sent_models == ['old']
        assert meter.status()['model_identity'] == old_identity
        assert meter.status()['total_tokens'] == 19
    finally:
        release.set()
        server.shutdown(); server.server_close()
