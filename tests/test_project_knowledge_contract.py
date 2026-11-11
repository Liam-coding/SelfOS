"""Frozen test-first acceptance suite; missing next-generation capabilities fail explicitly."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import threading
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if importlib.util.find_spec('knowledge_pipeline'):
    import knowledge_pipeline as pipeline
else:
    import knowledge as pipeline


def api(name):
    function = getattr(pipeline, name, None)
    assert callable(function), f'Capability not implemented: {name}; see frozen acceptance contract'
    return function


def message(text, *, identity='m1', project='C:/projects/alpha', session='s1', role='user', timestamp='2026-11-10T08:00:00Z', **extra):
    return dict(id=identity, session_id=session, project_id=project, project=Path(project).name,
                role=role, text=text, timestamp=timestamp, source='codex', path=f'{session}.jsonl', **extra)


def card(**changes):
    value = dict(project_id='C:/projects/alpha', title='Alpha', intent='Reliable local import',
                 status='in_progress', decisions=['Use incremental import'], blockers=['Source validation'],
                 next_steps=['Repair invalid summaries'], source_ids=['m1'],
                 updated_at='2026-11-10T08:00:00Z', verified=False)
    value.update(changes)
    return value


def session(text='We are implementing reliable local import.', **changes):
    item = message(text, **changes)
    return dict(session_id=item['session_id'], project_id=item['project_id'],
                messages=[item], fingerprint='input-' + item['id'])


def summary(item, **changes):
    last = item['messages'][-1]
    update = card(project_id=item['project_id'], title=last['project'],
                  source_ids=[last['id']], updated_at=last['timestamp'], **changes)
    return {'project': update, 'lessons': []}


@pytest.mark.parametrize('text', [
    '继续', '再跑一次', '好的', '谢谢', '取消这次运行', '先停一下', '重试', '帮我打开终端',
    'continue', 'retry', 'run it again', 'thanks', 'ok', 'stop this run', 'open the terminal',
    '/clear', '/exit', 'git status',
])
def test_transient_standalone_requests_do_not_become_knowledge(text):
    assert api('compact_message')(message(text)) is None


@pytest.mark.parametrize('text', [
    '我在开发 SelfOS，把本地 AI 对话整理成知识库。',
    '选择增量导入，因为全量处理太慢。',
    '目前卡在来源 ID 校验，下一步补重试。',
    '这次不部署，等权限回归测试通过后再部署。',
    '取消按钮必须保留，否则用户无法停止长任务。',
    '继续保留原始来源，因为摘要可能需要审计。',
    '好的方案是按项目合并，而不是按消息追加。',
    'I am building Alpha to make local imports reliable.',
    'We chose SQLite because concurrent writes need transactions.',
    'The blocker is an invalid source ID in the model response.',
    'Do not deploy yet; the regression test is failing.',
    'The cancel feature is required for long-running tasks.',
    'My recurring preference is concise Chinese explanations.',
    'Next step: benchmark incremental import against full history.',
])
def test_explicit_project_intent_decisions_and_blockers_survive_filtering(text):
    result = api('compact_message')(message(text))
    assert result is not None
    assert result['id'] == 'm1'
    assert text in result['text']


@pytest.mark.parametrize('language,body,symbol', [
    ('python', 'def import_records(records):\n' + '    value = 123456789\n' * 1000, 'import_records'),
    ('javascript', 'function importRecords(records) {\n' + 'const value = 123456789;\n' * 1000 + '}', 'importRecords'),
    ('java', 'public void importRecords() {\n' + 'int value = 123456789;\n' * 1000 + '}', 'importRecords'),
    ('sql', 'CREATE TABLE session_cache (\n' + 'column_name VARCHAR(100),\n' * 1000 + ');', 'session_cache'),
])
def test_bulk_code_is_compacted_but_change_purpose_and_symbols_survive(language, body, symbol):
    text = 'Fix duplicate imports by caching completed sessions in importer.py.\n' + chr(96)*3 + language + '\n' + body + '\n' + chr(96)*3
    result = api('compact_message')(message(text, role='assistant'))
    assert result is not None
    assert len(result['text']) < len(text) * 0.3
    assert 'duplicate imports' in result['text']
    assert 'importer.py' in result['text']
    assert symbol in result['text']
    assert result['id'] == 'm1'


def test_code_compaction_preserves_failure_and_next_step_after_long_body():
    text = 'Fix source validation.\n' + chr(96)*3 + 'python\n' + 'x = 1\n' * 5000 + chr(96)*3 + '\nTests still fail with ValueError: unknown source. Next: repair source mapping.'
    result = api('compact_message')(message(text, role='assistant'))
    assert 'ValueError: unknown source' in result['text']
    assert 'repair source mapping' in result['text']
    assert len(result['text']) < len(text) * 0.3


def test_secrets_are_redacted_before_summarization():
    result = api('compact_message')(message('The importer must redact person@example.com before sending conversations.'))
    assert result is not None
    assert 'person@example.com' not in result['text']
    assert 'redact' in result['text']


def test_unrelated_tool_output_is_not_durable_knowledge():
    assert api('compact_message')(message('Directory listing: hundreds of temporary files', role='tool')) is None


def test_relevant_test_failure_is_kept_as_evidence():
    result = api('compact_message')(message('FAILED test_import_idempotency', role='tool',
        verification={'command': 'pytest tests/test_import.py', 'exit_code': 1, 'relevant': True}))
    assert result is not None
    assert result['verification']['exit_code'] == 1
    assert 'test_import_idempotency' in result['text']


@pytest.mark.parametrize('items,expected', [
    ([], 0),
    ([message('continue'), message('retry', identity='m2')], 0),
    ([message('We are building reliable import.')], 1),
    ([message('We are building reliable import.'), message('We are fixing validation.', identity='m2', session='s2')], 2),
    ([message('We are building Alpha.'), message('We are building Beta.', identity='m2', project='C:/projects/beta', session='s2')], 2),
])
def test_session_grouping_has_no_empty_or_mixed_project_work(items, expected):
    sessions = api('prepare_sessions')(items)
    assert len(sessions) == expected
    for item in sessions:
        assert item['messages']
        assert {m['project_id'] for m in item['messages']} == {item['project_id']}
        assert {m['session_id'] for m in item['messages']} == {item['session_id']}


def test_messages_are_chronological_within_original_session():
    items = [message('Now blocked by source validation.', identity='m2', timestamp='2026-11-10T09:00:00Z'),
             message('Start the incremental import feature.', timestamp='2026-11-10T08:00:00Z')]
    result = api('prepare_sessions')(items)
    assert [m['id'] for m in result[0]['messages']] == ['m1', 'm2']


def test_copied_message_records_are_not_summarized_twice():
    item = message('We chose incremental import to reduce API calls.')
    sessions = api('prepare_sessions')([item, copy.deepcopy(item)])
    assert [m['id'] for s in sessions for m in s['messages']] == ['m1']


def test_project_basename_collision_does_not_merge_unrelated_projects():
    items = [message('Work on client A import.', project='C:/client-a/app'),
             message('Work on client B import.', identity='m2', project='C:/client-b/app', session='s2')]
    result = api('prepare_sessions')(items)
    assert {s['project_id'] for s in result} == {'C:/client-a/app', 'C:/client-b/app'}


def test_session_fingerprint_changes_when_outcome_changes():
    prepare = api('prepare_sessions')
    old = prepare([message('The import is still failing.')])[0]
    new = prepare([message('The import is now passing.')])[0]
    assert old['fingerprint'] != new['fingerprint']


def test_session_fingerprint_is_stable_when_input_order_is_shuffled():
    prepare = api('prepare_sessions')
    items = [message('Implement source mapping.'), message('Tests are failing.', identity='m2', timestamp='2026-11-10T09:00:00Z')]
    assert prepare(items)[0]['fingerprint'] == prepare(list(reversed(items)))[0]['fingerprint']


def test_every_retained_source_is_represented_after_compaction_and_splitting():
    items = [message('We need reliable imports. ' * 700, identity=f'm{i}', timestamp=f'2026-11-10T08:0{i}:00Z') for i in range(4)]
    sessions = api('prepare_sessions')(items, max_chars=4000)
    assert {m['id'] for s in sessions for m in s['messages']} == {'m0', 'm1', 'm2', 'm3'}
    assert all(sum(len(m['text']) for m in s['messages']) <= 4000 for s in sessions)


def test_same_project_has_latest_status_and_preserves_past_decisions():
    result = api('merge_project_card')(card(), card(status='blocked', blockers=['API quota'],
        decisions=['Add bounded concurrency'], source_ids=['m2'], updated_at='2026-11-10T09:00:00Z'))
    assert result['status'] == 'blocked'
    assert result['blockers'] == ['API quota']
    assert set(result['decisions']) == {'Use incremental import', 'Add bounded concurrency'}
    assert set(result['source_ids']) == {'m1', 'm2'}


def test_older_session_cannot_roll_back_current_project_status():
    result = api('merge_project_card')(card(status='completed', blockers=[], verified=True, updated_at='2026-11-10T10:00:00Z'), card())
    assert result['status'] == 'completed'
    assert result['blockers'] == []
    assert result['verified'] is True


def test_repeated_decision_is_not_appended_again():
    result = api('merge_project_card')(card(), card())
    assert result['decisions'] == ['Use incremental import']
    assert result['source_ids'] == ['m1']


def test_empty_new_intent_does_not_erase_project_purpose():
    result = api('merge_project_card')(card(), card(intent='', updated_at='2026-11-10T09:00:00Z'))
    assert result['intent'] == 'Reliable local import'


def test_resolved_blocker_does_not_remain_active():
    result = api('merge_project_card')(card(), card(status='in_progress', blockers=[], next_steps=['Benchmark'], updated_at='2026-11-10T09:00:00Z'))
    assert result['blockers'] == []
    assert result['next_steps'] == ['Benchmark']


def test_paused_project_is_not_reported_as_active():
    result = api('merge_project_card')(card(), card(status='paused', updated_at='2026-11-10T09:00:00Z'))
    assert result['status'] == 'paused'


def test_merge_does_not_mutate_caller_owned_inputs():
    first, second = card(), card(status='blocked')
    before = copy.deepcopy((first, second))
    api('merge_project_card')(first, second)
    assert (first, second) == before


def test_merge_rejects_cross_project_update():
    with pytest.raises(ValueError):
        api('merge_project_card')(card(), card(project_id='C:/projects/beta'))


@pytest.mark.parametrize('bad_sources', [[], ['unknown'], ['m1', 'unknown'], [123], 'm1'])
def test_untraceable_project_summary_is_rejected(bad_sources):
    item = session()
    candidate = summary(item)
    candidate['project']['source_ids'] = bad_sources
    with pytest.raises(ValueError):
        api('validate_summary')(candidate, item)


def test_assistant_completion_claim_is_not_verified_completion():
    item = session('I finished the implementation.', role='assistant')
    result = api('validate_summary')(summary(item, status='completed', verified=True), item)
    assert result['project']['status'] == 'reported_complete'
    assert result['project']['verified'] is False


def test_relevant_successful_test_evidence_supports_verified_completion():
    item = session('All import regression tests passed.', role='tool',
        verification={'command': 'pytest tests/test_import.py', 'exit_code': 0, 'relevant': True})
    result = api('validate_summary')(summary(item, status='completed', verified=True), item)
    assert result['project']['status'] == 'completed'
    assert result['project']['verified'] is True


def test_failed_test_evidence_cannot_support_verified_completion():
    item = session('FAILED test_import', role='tool',
        verification={'command': 'pytest tests/test_import.py', 'exit_code': 1, 'relevant': True})
    result = api('validate_summary')(summary(item, status='completed', verified=True), item)
    assert result['project']['verified'] is False
    assert result['project']['status'] != 'completed'


def test_summary_of_another_project_is_rejected():
    item = session()
    candidate = summary(item)
    candidate['project']['project_id'] = 'C:/projects/beta'
    with pytest.raises(ValueError):
        api('validate_summary')(candidate, item)


def test_valid_lesson_must_also_have_known_sources():
    item = session()
    candidate = summary(item)
    candidate['lessons'] = [{'text': 'Use bounded retries', 'source_ids': ['unknown'], 'kind': 'user_fact'}]
    with pytest.raises(ValueError):
        api('validate_summary')(candidate, item)


def cards_text(vault):
    return '\n'.join(p.read_text(encoding='utf-8') for p in (vault / '02_Work' / 'projects').glob('*.md'))


def test_successful_session_creates_a_sourced_project_card(tmp_path):
    result = api('consolidate_sessions')(tmp_path, [session()], summarize=summary)
    assert result['completed_sessions'] == 1
    assert result['failed_sessions'] == []
    text = cards_text(tmp_path)
    assert 'Reliable local import' in text
    assert 'Source validation' in text
    assert 'm1' in text


def test_unchanged_session_replay_does_not_call_model_or_duplicate_card(tmp_path):
    run = api('consolidate_sessions')
    item = session()
    run(tmp_path, [item], summarize=summary)
    original = cards_text(tmp_path)
    def forbidden(_):
        raise AssertionError('Unchanged cached session must not call the model')
    result = run(tmp_path, [copy.deepcopy(item)], summarize=forbidden)
    assert result['model_calls'] == 0
    assert cards_text(tmp_path) == original


def test_changed_session_is_resummarized_and_updates_project_state(tmp_path):
    run = api('consolidate_sessions')
    run(tmp_path, [session()], summarize=summary)
    changed = session('Now blocked by quota.', identity='m2', timestamp='2026-11-10T09:00:00Z')
    result = run(tmp_path, [changed], summarize=lambda s: summary(s, status='blocked', blockers=['Quota exhausted']))
    assert result['model_calls'] == 1
    assert 'Quota exhausted' in cards_text(tmp_path)


def test_temporary_api_failure_is_retried_before_session_is_lost(tmp_path):
    attempts = []
    def flaky(item):
        attempts.append(item['session_id'])
        if len(attempts) == 1:
            raise TimeoutError('temporary API timeout')
        return summary(item)
    result = api('consolidate_sessions')(tmp_path, [session()], summarize=flaky, max_attempts=2)
    assert result['completed_sessions'] == 1
    assert result['failed_sessions'] == []
    assert 'Reliable local import' in cards_text(tmp_path)


def test_invalid_source_response_is_retried_with_no_untraceable_writes(tmp_path):
    attempts = []
    def invalid_once(item):
        attempts.append(1)
        candidate = summary(item)
        if len(attempts) == 1:
            candidate['project']['source_ids'] = ['fabricated-source']
        return candidate
    result = api('consolidate_sessions')(tmp_path, [session()], summarize=invalid_once, max_attempts=2)
    assert result['completed_sessions'] == 1
    assert 'fabricated-source' not in cards_text(tmp_path)


def test_failed_session_does_not_abort_unrelated_project(tmp_path):
    items = [session(), session('Build Beta import.', identity='m2', session='s2', project='C:/projects/beta')]
    def fail_alpha(item):
        if item['session_id'] == 's1':
            raise ValueError('invalid summary')
        return summary(item)
    result = api('consolidate_sessions')(tmp_path, items, summarize=fail_alpha, max_attempts=2)
    assert result['completed_sessions'] == 1
    assert result['failed_sessions'] == ['s1']
    assert 'C:/projects/alpha' in result['missing_projects']
    assert 'beta' in cards_text(tmp_path)


def test_failed_session_is_not_cached_as_success(tmp_path):
    run = api('consolidate_sessions')
    def fail(_):
        raise TimeoutError('API unavailable')
    run(tmp_path, [session()], summarize=fail, max_attempts=1)
    result = run(tmp_path, [session()], summarize=summary)
    assert result['completed_sessions'] == 1
    assert result['model_calls'] == 1


def test_two_sessions_update_one_project_card_without_duplicate_files(tmp_path):
    items = [session(), session('Validation fixed.', identity='m2', session='s2', timestamp='2026-11-10T09:00:00Z')]
    api('consolidate_sessions')(tmp_path, items, summarize=summary)
    assert len(list((tmp_path / '02_Work' / 'projects').glob('*.md'))) == 1
    text = cards_text(tmp_path)
    assert 'm1' in text and 'm2' in text


def test_unrelated_existing_personal_file_is_preserved(tmp_path):
    (tmp_path / 'PROFILE.md').write_text('Confirmed personal profile', encoding='utf-8')
    api('consolidate_sessions')(tmp_path, [session()], summarize=summary)
    assert (tmp_path / 'PROFILE.md').read_text(encoding='utf-8') == 'Confirmed personal profile'


def test_reusable_lesson_is_separate_from_project_status(tmp_path):
    def with_lesson(item):
        candidate = summary(item)
        candidate['lessons'] = [{'text': 'Restart the service after changing loaded handlers.', 'source_ids': ['m1'], 'kind': 'user_fact'}]
        return candidate
    api('consolidate_sessions')(tmp_path, [session()], summarize=with_lesson)
    text = (tmp_path / '05_Life' / 'lessons.md').read_text(encoding='utf-8')
    assert 'Restart the service' in text
    assert 'm1' in text


def test_retry_count_is_bounded_and_failure_is_reported(tmp_path):
    def fail(_):
        raise TimeoutError('API unavailable')
    result = api('consolidate_sessions')(tmp_path, [session()], summarize=fail, max_attempts=2)
    assert result['model_calls'] == 2
    assert result['failed_sessions'] == ['s1']
    assert not list((tmp_path / '02_Work' / 'projects').glob('*.md'))


def test_all_noise_workload_makes_zero_model_calls(tmp_path):
    prepare = api('prepare_sessions')
    items = [message('continue', identity=f'm{i}') for i in range(1000)]
    def forbidden(_):
        raise AssertionError('Noise-only inputs must not call the model')
    result = api('consolidate_sessions')(tmp_path, prepare(items), summarize=forbidden)
    assert result['model_calls'] == 0
    assert result['missing_projects'] == []


def test_concurrency_is_bounded_and_independent_sessions_can_overlap(tmp_path):
    lock = threading.Lock()
    active, peak = 0, 0
    def slow(item):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return summary(item)
    items = [session('Build reliable import.', identity=f'm{i}', session=f's{i}', project=f'C:/projects/p{i}') for i in range(6)]
    result = api('consolidate_sessions')(tmp_path, items, summarize=slow, max_workers=2)
    assert result['completed_sessions'] == 6
    assert 1 < peak <= 2


def test_coverage_reports_active_project_without_card():
    items = [session(), session('Build Beta.', identity='m2', session='s2', project='C:/projects/beta')]
    result = api('audit_coverage')(items, [card()])
    assert result['missing_projects'] == ['C:/projects/beta']


def test_coverage_reports_no_missing_project_when_all_are_present():
    result = api('audit_coverage')([session()], [card()])
    assert result['missing_projects'] == []


def test_coverage_does_not_accept_a_same_basename_project_as_coverage():
    item = session('Build A.', project='C:/client-a/app')
    result = api('audit_coverage')([item], [card(project_id='C:/client-b/app')])
    assert result['missing_projects'] == ['C:/client-a/app']
