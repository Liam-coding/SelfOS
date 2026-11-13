from tests.test_auth_http import http
from tests.test_workload_preview import fixture_source
from selfos.sources.selection import save_sources
import selfos.web.server as runtime


def test_workload_preview_and_budget_require_auth_and_do_not_call_model(http, tmp_path, monkeypatch):
    request, auth = http
    assert request('/__knowledge_workload__')[0] == 401
    assert request('/__knowledge_budget__', {})[0] == 401
    auth.setup('synthetic workload password')
    cookie = 'selfos_session=' + auth.login('synthetic workload password')
    root = tmp_path / 'source'
    fixture_source(root)
    vault = tmp_path / 'app/vault'
    save_sources(vault, dict(roots=[str(root)], exclusions=[]))
    def forbidden(*args, **kwargs):
        raise AssertionError('Preview/save/status must not call a model')
    monkeypatch.setattr('selfos.providers.client.request_opener', forbidden)
    before = {p: p.read_bytes() for p in vault.rglob('*') if p.is_file()}
    code, data, _ = request('/__knowledge_workload__', cookie=cookie)
    assert code == 200 and data['pending_parts'] == 1
    assert data['estimate']['cost_usd'] is None
    assert before == {p: p.read_bytes() for p in vault.rglob('*') if p.is_file()}
    code, data, _ = request('/__knowledge_budget__', dict(max_requests=5, input_price=1.5, output_price=3), cookie)
    assert code == 200 and data['max_requests'] == 5 and data['pricing_known']
    status = request('/__knowledge_settings__', cookie=cookie)[1]
    assert status['usage']['budget']['max_requests'] == 5
    assert status['usage']['runs'] == []


def test_budget_rejects_invalid_and_active_job_changes(http, tmp_path, monkeypatch):
    request, auth = http
    auth.setup('synthetic workload password')
    cookie = 'selfos_session=' + auth.login('synthetic workload password')
    for patch in (dict(max_requests=0), dict(max_requests=True), dict(input_price=-1), dict(unknown=1)):
        assert request('/__knowledge_budget__', patch, cookie)[0] == 400
    monkeypatch.setattr(runtime, 'KNOWLEDGE_RUN', {'stop_file': tmp_path / 'stop'})
    assert request('/__knowledge_budget__', dict(max_requests=10), cookie)[0] == 409
    assert request('/__knowledge_workload__', cookie=cookie)[0] == 409
