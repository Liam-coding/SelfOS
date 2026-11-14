"""Real loopback provider adaptation and measured usage, never paid calls."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tests.test_knowledge_qa_service import qa_vault


@pytest.mark.parametrize('provider', ['anthropic', 'openai'])
@pytest.mark.parametrize('invalid', ['foreign_id', 'malformed', 'envelope', 'null_envelope', 'scalar_envelope'])
def test_qa_forced_output_repair_and_tokens(qa_vault, provider, invalid):
    from selfos.app.knowledge_qa import answer_question
    from selfos.providers.settings import save_config
    vault, _ = qa_vault
    captured = []
    class Model(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            captured.append(body)
            prompt = json.loads(next(message['content'] for message in body['messages'] if message['role'] == 'user'))
            identity = prompt['records'][0]['id']
            payload = dict(status='answered', answer='SQLite was selected for atomic writes.',
                           record_ids=['foreign' if len(captured) == 1 else identity], inferences=[])
            if invalid == 'malformed' and len(captured) == 1:
                payload = {'invalid': 'model output'}
            if provider == 'anthropic':
                result = dict(content=[dict(type='tool_use', name='answer_knowledge', input=payload)],
                              usage=dict(input_tokens=30, output_tokens=10))
            else:
                result = dict(choices=[dict(finish_reason='tool_calls', message=dict(tool_calls=[
                    dict(function=dict(name='answer_knowledge', arguments='not JSON' if invalid == 'malformed' and len(captured) == 1 else json.dumps(payload)))]))],
                    usage=dict(prompt_tokens=30, completion_tokens=10))
            if invalid == 'envelope' and len(captured) == 1:
                result = []
            elif invalid == 'null_envelope' and len(captured) == 1:
                result = None
            elif invalid == 'scalar_envelope' and len(captured) == 1:
                result = 42
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Model)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    save_config(vault.parent, dict(provider=provider, model='synthetic-model', api_key='synthetic-key',
        base_url=f'http://127.0.0.1:{server.server_port}' + ('/v1' if provider == 'openai' else ''), proxy_mode='direct'))
    try:
        result = answer_question(vault, vault.parent, 'Why SQLite?')
        assert result['status'] == 'answered' and len(captured) == 2
        assert all(body['model'] == 'synthetic-model' and body['tool_choice'] for body in captured)
        assert 'repair_feedback' in json.loads(next(message['content'] for message in captured[1]['messages'] if message['role'] == 'user'))
        assert str(vault.parent) not in json.dumps(captured)
        journals = list((vault / '.knowledge_usage').glob('*.json'))
        from selfos.storage.usage import RequestUsage
        assert len(journals) == 1
        usage = RequestUsage(vault, journals[0].stem, 2).status()
        assert usage['used'] == 2
        missing = invalid in ('envelope', 'null_envelope', 'scalar_envelope')
        assert usage['total_tokens'] == (40 if missing else 80)
        assert usage['complete_usage'] is (not missing)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
