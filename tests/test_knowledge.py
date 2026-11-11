import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import knowledge


def messages():
    return [{
        'id': 'source-1', 'role': 'user', 'text': 'I want to finish my research this month.',
        'timestamp': '2026-11-10T08:00:00Z', 'source': 'codex',
        'path': 'session.jsonl', 'project': 'research',
    }]


def proposal(batch, context):
    return [{'target': 'GOALS.md', 'facts': [{
        'text': 'Finish research this month.', 'source_ids': ['source-1'], 'kind': 'user_fact',
    }]}]


def test_extracts_both_roles_skips_tools_and_survives_bad_lines(tmp_path):
    path = tmp_path / 'session.jsonl'
    rows = [
        {'type': 'session_meta', 'payload': {'cwd': 'C:/research'}},
        {'type': 'response_item', 'timestamp': '2026-11-10T08:00:00Z', 'payload': {
            'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': 'I want to finish research this month.'}]}},
        {'type': 'response_item', 'timestamp': '2026-11-10T08:01:00Z', 'payload': {
            'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Try a weekly research review.'}]}},
        {'type': 'response_item', 'payload': {'type': 'function_call_output', 'role': 'assistant', 'content': 'tool secrets'}},
    ]
    path.write_text('broken json\n' + '\n'.join(json.dumps(x) for x in rows), encoding='utf-8')
    result = knowledge.extract_conversations([tmp_path])
    assert [x['role'] for x in result] == ['user', 'assistant']
    assert result[1]['text'] == 'Try a weekly research review.'
    assert result[0]['path'] == str(path)
    (tmp_path / 'copy.jsonl').write_bytes(path.read_bytes())
    assert len(knowledge.extract_conversations([tmp_path])) == 2


def test_extracts_claude_assistant_text_and_redacts_secrets(tmp_path):
    row = {'type': 'assistant', 'timestamp': '2026-11-10T08:00:00Z', 'message': {
        'content': [{'type': 'thinking', 'thinking': 'private reasoning'},
                    {'type': 'text', 'text': 'My email is person@example.com, review the research plan.'}]}}
    (tmp_path / 'claude.jsonl').write_text(json.dumps(row), encoding='utf-8')
    result = knowledge.extract_conversations([tmp_path])
    assert len(result) == 1
    assert 'person@example.com' not in result[0]['text']
    assert 'private reasoning' not in result[0]['text']


def test_codex_analysis_is_not_imported_as_conversation(tmp_path):
    rows = [
        {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant',
         'channel': 'analysis', 'content': [{'type': 'output_text', 'text': 'Internal reasoning about the user.'}]}},
        {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant',
         'channel': 'final', 'content': [{'type': 'output_text', 'text': 'A weekly review could help.'}]}},
    ]
    (tmp_path / 'codex.jsonl').write_text('\n'.join(json.dumps(x) for x in rows), encoding='utf-8')
    assert [x['text'] for x in knowledge.extract_conversations([tmp_path])] == ['A weekly review could help.']


def test_growing_vault_context_is_bounded_without_truncating_saved_knowledge(tmp_path):
    original = 'Existing knowledge.\n' * 10000
    (tmp_path / 'GOALS.md').write_text(original, encoding='utf-8')
    def generate(batch, context):
        assert len(context['GOALS.md']) < 5000
        return proposal(batch, context)
    knowledge.import_knowledge(tmp_path, messages(), generate=generate)
    assert (tmp_path / 'GOALS.md').read_text(encoding='utf-8').startswith(original.rstrip())


def test_batches_preserve_long_message_tail():
    items = messages()
    items[0]['text'] = 'a' * 30000 + 'TAIL'
    batches = knowledge.build_batches(items, max_chars=4000)
    assert len(batches) > 1
    assert ''.join(m['text'] for batch in batches for m in batch) == items[0]['text']
    assert all(sum(len(m['text']) for m in batch) <= 4000 for batch in batches)


def test_direct_write_preserves_original_backs_up_and_deduplicates(tmp_path):
    vault = tmp_path / 'vault'
    vault.mkdir()
    (vault / 'GOALS.md').write_text('# Goals\nExisting confirmed goal.\n', encoding='utf-8')
    result = knowledge.import_knowledge(vault, messages(), generate=proposal)
    text = (vault / 'GOALS.md').read_text(encoding='utf-8')
    assert 'Existing confirmed goal.' in text
    assert 'Finish research this month.' in text
    assert 'source-1' in text and '2026-11-10T08:00:00Z' in text
    assert result['facts'] == 1
    saved = list((vault / '.knowledge_backups' / result['run_id']).rglob('GOALS.md'))
    assert len(saved) == 1
    assert saved[0].read_text(encoding='utf-8') == '# Goals\nExisting confirmed goal.\n'
    again = knowledge.import_knowledge(vault, messages(), generate=proposal)
    assert again['facts'] == 0
    assert (vault / 'GOALS.md').read_text(encoding='utf-8') == text


@pytest.mark.parametrize('target', ['../outside.md', '/tmp/outside.md', '90_Inbox/data.md', '91_Staging/x.md', 'GOALS.md/child.md'])
def test_rejects_invalid_targets_before_any_write(tmp_path, target):
    def invalid(batch, context):
        return proposal(batch, context) + [{'target': target, 'facts': [{
            'text': 'Bad change', 'source_ids': ['source-1'], 'kind': 'user_fact'}]}]
    with pytest.raises(ValueError):
        knowledge.import_knowledge(tmp_path, messages(), generate=invalid)
    assert not (tmp_path / 'GOALS.md').exists()
    assert not (tmp_path / '.knowledge_state.json').exists()


def test_rejects_untraceable_fact(tmp_path):
    def invalid(batch, context):
        result = proposal(batch, context)
        result[0]['facts'][0]['source_ids'] = ['unknown']
        return result
    with pytest.raises(ValueError):
        knowledge.import_knowledge(tmp_path, messages(), generate=invalid)
    assert not (tmp_path / 'GOALS.md').exists()


def test_assistant_statement_cannot_become_confirmed_user_fact(tmp_path):
    items = messages()
    items[0]['role'] = 'assistant'
    knowledge.import_knowledge(tmp_path, items, generate=proposal)
    assert '[assistant-suggestion]' in (tmp_path / 'GOALS.md').read_text(encoding='utf-8')


def test_api_failure_is_retryable(tmp_path):
    def fail(batch, context):
        raise RuntimeError('API unavailable')
    with pytest.raises(RuntimeError):
        knowledge.import_knowledge(tmp_path, messages(), generate=fail)
    assert not (tmp_path / '.knowledge_state.json').exists()
    assert knowledge.import_knowledge(tmp_path, messages(), generate=proposal)['facts'] == 1


def test_restore_returns_original_and_allows_reimport(tmp_path):
    (tmp_path / 'GOALS.md').write_text('original', encoding='utf-8')
    result = knowledge.import_knowledge(tmp_path, messages(), generate=proposal)
    knowledge.restore_backup(tmp_path, result['run_id'])
    assert (tmp_path / 'GOALS.md').read_text(encoding='utf-8') == 'original'
    assert knowledge.import_knowledge(tmp_path, messages(), generate=proposal)['facts'] == 1


def test_restore_removes_newly_created_files(tmp_path):
    result = knowledge.import_knowledge(tmp_path, messages(), generate=proposal)
    knowledge.restore_backup(tmp_path, result['run_id'])
    assert not (tmp_path / 'GOALS.md').exists()


def test_later_batch_failure_preserves_completed_batch_and_retries_only_tail(tmp_path):
    items = messages()
    items[0]['text'] = 'a' * 12000
    items.append(dict(items[0], id='source-2', text='A second research goal.'))
    def fail_second(batch, context):
        if batch[0]['id'] == 'source-2':
            raise RuntimeError('network failure')
        return proposal(batch, context)
    with pytest.raises(RuntimeError):
        knowledge.import_knowledge(tmp_path, items, generate=fail_second)
    assert 'Finish research this month.' in (tmp_path / 'GOALS.md').read_text(encoding='utf-8')
    def retry(batch, context):
        assert [x['id'] for x in batch] == ['source-2']
        return [{'target': 'GOALS.md', 'facts': [{
            'text': 'Second goal.', 'source_ids': ['source-2'], 'kind': 'user_fact'}]}]
    result = knowledge.import_knowledge(tmp_path, items, generate=retry)
    assert result['facts'] == 1
    assert (tmp_path / 'GOALS.md').read_text(encoding='utf-8').count('Finish research this month.') == 1


def test_disk_failure_rolls_back_canonical_writes(tmp_path, monkeypatch):
    (tmp_path / 'GOALS.md').write_text('original', encoding='utf-8')
    real = knowledge._atomic_write
    def fail_state(path, data):
        if path == tmp_path / '.knowledge_state.json':
            raise OSError('disk full')
        return real(path, data)
    monkeypatch.setattr(knowledge, '_atomic_write', fail_state)
    with pytest.raises(OSError):
        knowledge.import_knowledge(tmp_path, messages(), generate=proposal)
    assert (tmp_path / 'GOALS.md').read_text(encoding='utf-8') == 'original'
    assert not (tmp_path / '.knowledge_state.json').exists()
    assert not (tmp_path / '.knowledge.lock').exists()


def test_restore_refuses_to_overwrite_later_manual_edit(tmp_path):
    result = knowledge.import_knowledge(tmp_path, messages(), generate=proposal)
    (tmp_path / 'GOALS.md').write_text('manual change', encoding='utf-8')
    with pytest.raises(ValueError, match='changed after'):
        knowledge.restore_backup(tmp_path, result['run_id'])
    assert (tmp_path / 'GOALS.md').read_text(encoding='utf-8') == 'manual change'


def test_missing_credentials_fails_before_scanning(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.setattr(sys, 'argv', ['knowledge.py', '--vault', str(tmp_path / 'vault')])
    with pytest.raises(SystemExit) as failure:
        knowledge.main()
    assert failure.value.code == 1
    assert 'ANTHROPIC_API_KEY is missing' in capsys.readouterr().out
    assert not (tmp_path / 'vault').exists()


def test_concurrent_import_does_not_remove_existing_lock(tmp_path):
    (tmp_path / '.knowledge.lock').write_text('another process', encoding='utf-8')
    with pytest.raises(RuntimeError, match='already running'):
        knowledge.import_knowledge(tmp_path, messages(), generate=proposal)
    assert (tmp_path / '.knowledge.lock').read_text(encoding='utf-8') == 'another process'


def test_http_knowledge_stream_runs_pipeline_and_reports_exit(monkeypatch):
    import io
    import threading
    from http.server import HTTPServer
    from urllib.request import urlopen
    import serve
    class Process:
        returncode = 0
        stdout = io.StringIO('Knowledge complete: 1 facts, 1 files\n')
        def poll(self):
            return 0
    def launch(cmd, **kwargs):
        assert Path(cmd[2]).name == 'knowledge.py'
        assert '--stop-file' in cmd
        assert '-u' in cmd
        return Process()
    monkeypatch.setattr(serve.subprocess, 'Popen', launch)
    server = HTTPServer(('127.0.0.1', 0), serve.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f'http://127.0.0.1:{server.server_port}/__knowledge_stream__') as response:
            events = [json.loads(line[6:]) for line in response.read().decode().splitlines() if line.startswith('data: ')]
        assert events[0]['line'] == 'Knowledge complete: 1 facts, 1 files'
        assert events[-1] == {'done': True, 'ok': True, 'cancelled': False}
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
