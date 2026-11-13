from tests.test_auth_http import http
import selfos.web.server as runtime


def test_usage_and_allowance_require_auth_without_model_calls(http, tmp_path, monkeypatch):
    request, auth = http
    assert request('/__knowledge_usage__')[0] == 401
    assert request('/__knowledge_budget__', {})[0] == 401
    auth.setup('synthetic workload password')
    cookie = 'selfos_session=' + auth.login('synthetic workload password')
    def forbidden(*args, **kwargs):
        raise AssertionError('Usage/save must not call a model or scan sources')
    monkeypatch.setattr('selfos.providers.client.request_opener', forbidden)
    monkeypatch.setattr('selfos.sources.conversations.extract_conversations', forbidden)
    code, data, _ = request('/__knowledge_usage__', cookie=cookie)
    assert code == 200 and data['runs'] == []
    code, data, _ = request('/__knowledge_budget__', dict(max_requests=5), cookie)
    assert code == 200 and data == {'max_requests': 5}
    monkeypatch.setattr(runtime, 'KNOWLEDGE_RUN', {'stop_file': tmp_path / 'stop'})
    assert request('/__knowledge_usage__', cookie=cookie)[0] == 200
    assert request('/__knowledge_budget__', dict(max_requests=10), cookie)[0] == 409


def test_budget_rejects_prices_and_invalid_values(http, tmp_path):
    request, auth = http
    auth.setup('synthetic workload password')
    cookie = 'selfos_session=' + auth.login('synthetic workload password')
    for patch in (dict(max_requests=0), dict(max_requests=True), dict(input_price=1), dict(output_price=1), dict(unknown=1)):
        assert request('/__knowledge_budget__', patch, cookie)[0] == 400
