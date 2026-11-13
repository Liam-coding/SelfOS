"""Actual HTTP attempts and provider observations drive organization accounting."""
import json
import os
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request

import pytest


def test_attempt_limit_persists_across_openers_and_counts_http_errors(tmp_path):
    from selfos.storage.usage import RequestUsage
    from selfos.storage.onboarding import ModelBudgetExceeded
    from selfos.providers.client import request_opener
    from selfos.providers.settings import save_config
    sent = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            sent.append(self.rfile.read(int(self.headers['Content-Length'])))
            self.send_response(503)
            self.end_headers()
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    save_config(tmp_path, {'provider': 'openai', 'model': 'fixture', 'base_url': f'http://127.0.0.1:{server.server_port}/v1', 'proxy_mode': 'direct'})
    request = Request('http://placeholder', data=json.dumps({'messages': [], 'max_tokens': 1}).encode())
    vault = tmp_path / 'vault'
    try:
        for _ in range(3):
            with pytest.raises(RuntimeError, match='HTTP 503'):
                request_opener(tmp_path, budget=RequestUsage(vault, 'a' * 32, 3))(request)
        with pytest.raises(ModelBudgetExceeded):
            request_opener(tmp_path, budget=RequestUsage(vault, 'a' * 32, 3))(request)
        result = RequestUsage(vault, 'a' * 32, 3).status()
        assert len(sent) == result['used'] == result['failed_attempts'] == 3
        assert result['remaining'] == 0 and result['missing_usage'] == 3
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_concurrent_requests_cannot_overspend_and_observations_are_idempotent(tmp_path):
    from selfos.storage.usage import RequestUsage
    from selfos.storage.onboarding import ModelBudgetExceeded
    def claim(_):
        meter = RequestUsage(tmp_path, 'b' * 32, 4)
        try:
            ticket = meter.claim()
        except ModelBudgetExceeded:
            return False
        response = {'usage': {'prompt_tokens': 20, 'completion_tokens': 5}}
        meter.observe(ticket, response, 'openai')
        meter.observe(ticket, response, 'openai')
        return True
    with ThreadPoolExecutor(max_workers=8) as workers:
        outcomes = list(workers.map(claim, range(12)))
    result = RequestUsage(tmp_path, 'b' * 32, 4).status()
    assert sum(outcomes) == result['used'] == 4
    assert result['input_tokens'] == 80 and result['output_tokens'] == 20
    assert result['missing_usage'] == 0


@pytest.mark.parametrize('usage', [None, {'prompt_tokens': True, 'completion_tokens': 3}, {'prompt_tokens': -1, 'completion_tokens': 3}, {'prompt_tokens': 2}])
def test_invalid_or_missing_usage_is_unknown_instead_of_zero(tmp_path, usage):
    from selfos.storage.usage import RequestUsage
    meter = RequestUsage(tmp_path, 'c' * 32, 5)
    ticket = meter.claim()
    meter.observe(ticket, {'usage': usage}, 'openai')
    assert meter.status()['missing_usage'] == 1
    assert meter.status()['complete_usage'] is False


def test_pending_attempt_and_cached_billing_remain_visible(tmp_path):
    from selfos.storage.usage import RequestUsage
    meter = RequestUsage(tmp_path, 'd' * 32, 4)
    first = meter.claim()
    meter.observe(first, {'usage': {'input_tokens': 12, 'output_tokens': 7, 'cache_read_input_tokens': 100}}, 'anthropic')
    meter.claim()  # A process exits before a response; the attempt remains charged.
    result = RequestUsage(tmp_path, 'd' * 32, 4).status()
    assert result['used'] == 2 and result['missing_usage'] == 1
    assert result['cache_read_tokens'] == 100
    assert result['input_tokens'] == 112 and result['output_tokens'] == 7


def test_read_only_status_and_invalid_identity_create_nothing(tmp_path):
    from selfos.storage.usage import RequestUsage
    assert RequestUsage(tmp_path, 'e' * 32, 100).status()['used'] == 0
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError):
        RequestUsage(tmp_path, '../escape', 100)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.name != 'nt', reason='Windows extended path spelling')
def test_windows_extended_path_resolution_does_not_reject_contained_metadata(tmp_path, monkeypatch):
    from selfos.storage.usage import RequestUsage
    original = Path.resolve
    def extended(path, *args, **kwargs):
        resolved = original(path, *args, **kwargs)
        if path.suffix == '.json':
            return Path(chr(92) * 2 + '?' + chr(92) + str(resolved))
        return resolved
    monkeypatch.setattr(Path, 'resolve', extended)
    meter = RequestUsage(tmp_path, 'f' * 32, 3)
    assert meter.claim() == 1
    assert meter.status()['used'] == 1


def test_journal_with_duplicate_numeric_ticket_spellings_is_rejected(tmp_path):
    from selfos.storage.usage import RequestUsage
    folder = tmp_path / '.knowledge_usage'
    folder.mkdir()
    (folder / (('f' * 32) + '.json')).write_text(json.dumps({'version': 1, 'used': 2,
        'attempts': {'1': {'status': 'pending'}, '01': {'status': 'pending'}}, 'elapsed_seconds': 0, 'run_started': None}))
    with pytest.raises(ValueError):
        RequestUsage(tmp_path, 'f' * 32, 3).status()


@pytest.mark.parametrize('patch', [{'max_requests': True}, {'max_requests': 0}, {'max_requests': 10001}, {'input_price': -1}, {'output_price': float('nan')}, {'api_key': 'secret'}])
def test_budget_settings_reject_invalid_values_without_writes(tmp_path, patch):
    from selfos.app.budget import save_budget
    with pytest.raises(ValueError):
        save_budget(tmp_path / 'vault', tmp_path, patch)
    assert not (tmp_path / 'vault').exists()
