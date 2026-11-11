import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import knowledge


def batch():
    return [{'id': 'source-1', 'role': 'user', 'text': 'Use incremental imports.',
             'timestamp': '2026-11-10T08:00:00Z', 'source': 'codex',
             'path': 'synthetic.jsonl', 'project': 'Synthetic'}]


def updates(**changes):
    fact = {'text': 'Use incremental imports.', 'source_ids': ['source-1'], 'kind': 'user_fact'}
    fact.update(changes)
    return [{'target': 'GOALS.md', 'facts': [fact]}]


@pytest.mark.parametrize('text', ['', '   ', None, 12, [], {}])
def test_invalid_text_identifies_field_without_including_content(text):
    with pytest.raises(ValueError, match=r'updates\[0\]\.facts\[0\]\.text'):
        knowledge._validate_updates(updates(text=text), batch())


def test_long_text_requires_rewrite_instead_of_silent_truncation():
    with pytest.raises(ValueError, match='4000'):
        knowledge._validate_updates(updates(text='a'*4001), batch())


def test_text_boundary_after_whitespace_normalization():
    text = 'x '*1999 + 'ok'
    result = knowledge._validate_updates(updates(text='  ' + text + '\n'), batch())
    assert result[0][1] == text


def test_exact_single_source_string_can_be_safely_normalized():
    result = knowledge._validate_updates(updates(source_ids='source-1'), batch())
    assert result[0][2] == ['source-1']


def test_source_whitespace_and_duplicates_are_normalized():
    result = knowledge._validate_updates(updates(source_ids=[' source-1 ', 'source-1']), batch())
    assert result[0][2] == ['source-1']


@pytest.mark.parametrize('sources', [None, [], ['unknown'], ['source-1', 'unknown'], [1], ['source']])
def test_missing_or_invented_source_is_not_guessed(sources):
    with pytest.raises(ValueError, match=r'\.source_ids'):
        knowledge._validate_updates(updates(source_ids=sources), batch())


@pytest.mark.parametrize('kind,expected', [
    (' user_fact ', 'user_fact'), ('USER_FACT', 'user_fact'),
    ('fact', 'user_fact'), ('user', 'user_fact'),
    ('suggestion', 'assistant_suggestion'), ('assistant', 'assistant_suggestion'),
    ('ai_inference', 'inference'), ('ai-inference', 'inference'),
    ('inferred', 'inference'), (None, 'inference'),
])
def test_unambiguous_kind_aliases_are_normalized_conservatively(kind, expected):
    assert knowledge._validate_updates(updates(kind=kind), batch())[0][3] == expected


@pytest.mark.parametrize('kind', ['project', 'confirmed_forever', 123, [], {}])
def test_unsupported_kind_has_actionable_field_error(kind):
    with pytest.raises(ValueError, match=r'\.kind'):
        knowledge._validate_updates(updates(kind=kind), batch())


def test_alias_cannot_upgrade_assistant_advice_to_user_statement():
    items = batch()
    items[0]['role'] = 'assistant'
    assert knowledge._validate_updates(updates(kind='fact'), items)[0][3] == 'assistant_suggestion'


def test_all_three_invalid_fields_are_reported_in_one_repair_request():
    with pytest.raises(ValueError) as failure:
        knowledge._validate_updates(updates(text='', source_ids=['unknown'], kind='project'), batch())
    message = str(failure.value)
    assert '.text' in message
    assert '.source_ids' in message
    assert '.kind' in message


def test_api_receives_repair_feedback_separately_from_vault_context(monkeypatch):
    generate, requests = api_with_response(monkeypatch, json.dumps(updates(source_ids=['s1'])))
    generate(batch(), {'GOALS.md': 'Existing goal', '_validation_feedback': 'facts[0].source_ids is invalid'})
    prompt = json.loads(requests[0]['messages'][0]['content'])
    assert prompt['repair_feedback'] == 'facts[0].source_ids is invalid'
    assert prompt['vault_context'] == {'GOALS.md': 'Existing goal'}


def test_long_fact_is_repaired_on_retry_and_not_truncated(tmp_path):
    seen = []
    def generate(items, context):
        seen.append(context)
        return updates(text='a'*4001) if len(seen) == 1 else updates()
    result = knowledge.import_knowledge(tmp_path, batch(), generate)
    assert result['facts'] == 1
    assert len(seen) == 2
    assert '4000' in seen[1]['_validation_feedback']
    text = (tmp_path / 'GOALS.md').read_text(encoding='utf-8')
    assert 'Use incremental imports.' in text
    assert 'a'*100 not in text


def test_invalid_source_is_regenerated_before_any_canonical_write(tmp_path):
    seen = []
    def generate(items, context):
        seen.append(1)
        if len(seen) == 1:
            assert not (tmp_path / 'GOALS.md').exists()
            return updates(source_ids=['invented'])
        return updates()
    result = knowledge.import_knowledge(tmp_path, batch(), generate)
    assert result['facts'] == 1
    assert len(seen) == 2
    assert 'invented' not in (tmp_path / 'GOALS.md').read_text(encoding='utf-8')


def test_invalid_kind_is_regenerated_instead_of_dropping_batch(tmp_path):
    seen = []
    def generate(items, context):
        seen.append(1)
        return updates(kind='project') if len(seen) == 1 else updates(kind='inference')
    knowledge.import_knowledge(tmp_path, batch(), generate)
    assert len(seen) == 2
    assert '[ai-inference]' in (tmp_path / 'GOALS.md').read_text(encoding='utf-8')


def test_persistent_validation_failure_is_bounded_and_retryable(tmp_path):
    seen = []
    def generate(items, context):
        seen.append(1)
        return updates(source_ids=['unknown'])
    with pytest.raises(ValueError, match='source_ids'):
        knowledge.import_knowledge(tmp_path, batch(), generate, max_attempts=3)
    assert len(seen) == 3
    assert not (tmp_path / 'GOALS.md').exists()
    assert not (tmp_path / '.knowledge_state.json').exists()
    assert not (tmp_path / '.knowledge.lock').exists()
    assert knowledge.import_knowledge(tmp_path, batch(), lambda *_: updates())['facts'] == 1


def test_validation_diagnostic_is_local_and_redacted(tmp_path):
    def bad(*_):
        return updates(text='Do not save person@example.com.', source_ids=['unknown'])
    with pytest.raises(ValueError):
        knowledge.import_knowledge(tmp_path, batch(), bad, max_attempts=1)
    diagnostics = list((tmp_path / '.knowledge_errors').rglob('*.json'))
    assert len(diagnostics) == 1
    text = diagnostics[0].read_text(encoding='utf-8')
    assert 'source_ids' in text
    assert 'person@example.com' not in text
    assert 'source-1' in text


def api_with_response(monkeypatch, raw, *, stop_reason='end_turn'):
    requests = []
    monkeypatch.setattr(knowledge, '_get_api_config', lambda _: ('synthetic-key', 'https://synthetic.invalid'))
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def read(self):
            return json.dumps({'content': [{'text': raw}], 'stop_reason': stop_reason}).encode()
    def open_request(request, **_):
        requests.append(json.loads(request.data))
        return Response()
    monkeypatch.setattr(knowledge, 'urlopen', open_request)
    monkeypatch.setattr(__import__('model_client'), 'request_opener', lambda root: knowledge.urlopen)
    return knowledge.api_generator(Path('.')), requests


def test_api_uses_short_source_aliases_and_restores_original_ids(monkeypatch):
    generate, requests = api_with_response(monkeypatch, json.dumps(updates(source_ids=['s1'])))
    result = generate(batch(), {})
    prompt = json.loads(requests[0]['messages'][0]['content'])
    assert prompt['conversations'][0]['id'] == 's1'
    assert result[0]['facts'][0]['source_ids'] == ['source-1']
    assert knowledge._validate_updates(result, batch())[0][2] == ['source-1']


def test_api_unknown_alias_is_not_mapped_to_nearest_source(monkeypatch):
    generate, _ = api_with_response(monkeypatch, json.dumps(updates(source_ids=['s2'])))
    with pytest.raises(ValueError, match='source_ids'):
        knowledge._validate_updates(generate(batch(), {}), batch())


def test_api_accepts_fenced_json_and_updates_wrapper(monkeypatch):
    raw = chr(96)*3 + 'json\n' + json.dumps({'updates': updates(source_ids='s1')}) + '\n' + chr(96)*3
    generate, _ = api_with_response(monkeypatch, raw)
    assert knowledge._validate_updates(generate(batch(), {}), batch())[0][2] == ['source-1']


def test_api_parse_error_keeps_raw_response_for_local_diagnostics(monkeypatch):
    generate, _ = api_with_response(monkeypatch, 'not valid json')
    with pytest.raises(ValueError) as failure:
        generate(batch(), {})
    assert getattr(failure.value, 'raw_response', '') == 'not valid json'


def test_truncated_api_response_is_never_accepted(monkeypatch):
    generate, _ = api_with_response(monkeypatch, json.dumps(updates(source_ids=['s1'])), stop_reason='max_tokens')
    with pytest.raises(ValueError, match='truncated'):
        generate(batch(), {})


@pytest.mark.parametrize('raw', [
    '```json\n[]\n```\n\nThis input contains only transient browser logs.',
    'Here is the result:\n```json\n[]\n```\nNo enduring facts were found.',
    '```JSON\r\n[]\r\n```\r\nOnly debug output.',
    '[]\n\nNo enduring facts were found.',
])
def test_valid_empty_json_with_explanation_does_not_trigger_retry(monkeypatch, raw):
    generate, _ = api_with_response(monkeypatch, raw)
    assert generate(batch(), {}) == []


def test_fenced_facts_with_explanation_preserve_sources(monkeypatch):
    raw = '```json\n' + json.dumps(updates(source_ids=['s1'])) + '\n```\nThe fact is explicitly supported by the user.'
    generate, _ = api_with_response(monkeypatch, raw)
    assert knowledge._validate_updates(generate(batch(), {}), batch())[0][2] == ['source-1']


@pytest.mark.parametrize('raw', [
    '```json\n[]\n```\n```json\n[]\n```',
    '[]\n[]',
    '[]\n{"updates": []}',
    '```json\n[broken]\n```\nThe correct answer would be [].',
    'No durable facts were found.',
    '```json\n[]',
    '```python\n[]\n```',
])
def test_ambiguous_malformed_or_missing_json_is_still_rejected(monkeypatch, raw):
    generate, _ = api_with_response(monkeypatch, raw)
    with pytest.raises(ValueError):
        generate(batch(), {})


def test_explanation_after_empty_json_is_cached_without_extra_model_calls(tmp_path, monkeypatch):
    generate, requests = api_with_response(monkeypatch, '```json\n[]\n```\nOnly diagnostic logs, no durable facts.')
    first = knowledge.import_knowledge(tmp_path, batch(), generate)
    assert first['facts'] == 0
    assert len(requests) == 1
    assert not list((tmp_path / '.knowledge_errors').rglob('*.json'))
    knowledge.import_knowledge(tmp_path, batch(), generate)
    assert len(requests) == 1
