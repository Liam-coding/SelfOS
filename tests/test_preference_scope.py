"""Source-backed applicability and chronology regressions, no model calls."""
import copy
import itertools
import json
import runpy
from pathlib import Path

import pytest

from selfos.knowledge.records import merge_records, validate_record
from selfos.knowledge.settings import DEFAULT_SETTINGS


def preference(value, at='2026-01-01T10:00:00Z', scope=None, identity='m1', **extra):
    quote = 'I prefer ' + value + ' explanations.'
    raw = dict(key='communication.detail', value=value, text=quote, domain='personal',
               kind='user_fact', temporal='current', source_ids=[identity], evidence=quote, **extra)
    if scope is not None:
        raw['scope'] = scope
    session = {'project_id': 'project-alpha', 'messages': [
        {'id': identity, 'role': 'user', 'text': quote, 'timestamp': at}]}
    return validate_record(raw, session)


def merge(*records):
    state = {}
    merge_records(state, 'preferences', records, DEFAULT_SETTINGS)
    return state


def test_all_five_supplied_candidate_sequence_scenarios():
    root = Path(__file__).resolve().parents[1]
    evaluate = runpy.run_path(str(root / 'evals/run_preference_holdout.py'))['evaluate']
    report = evaluate(json.loads((root / 'evals/preference_holdout.json').read_text(encoding='utf-8')))
    assert report['sequence_passes'] == 5, report['sequences']
    assert report['model_calls'] == 0


def test_typed_scope_separates_global_activity_project_and_unknown():
    values = [preference('concise', scope={'type': 'global', 'id': ''}),
              preference('detailed', scope={'type': 'activity', 'id': 'research'}, identity='m2'),
              preference('bullets', scope={'type': 'project', 'id': 'current-project'}, identity='m3'),
              preference('plain', identity='m4')]
    state = merge(*values)
    assert {(r['scope_type'], r['scope'], r['value']) for r in state['preferences']} == {
        ('global', 'global', 'concise'), ('activity', 'research', 'detailed'),
        ('project', 'project-alpha', 'bullets'), ('unknown', 'unknown', 'plain')}
    assert not state['records_history']
    assert not any(r.get('conflict') for r in state['preferences'])


@pytest.mark.parametrize('scope', [
    {'type': 'global', 'id': 'research'}, {'type': 'unknown', 'id': 'work'},
    {'type': 'activity', 'id': ''}, {'type': 'project', 'id': 'another-project'},
    {'type': 'other', 'id': ''}, {'type': 'activity', 'id': '../private'},
    {'type': 'activity', 'id': 'research', 'extra': True}, 42, []])
def test_invalid_applicability_metadata_is_rejected(scope):
    with pytest.raises(ValueError, match='scope'):
        preference('concise', scope=scope)


def test_legacy_missing_scope_is_unknown_and_not_merged_with_global():
    unknown = preference('concise')
    global_record = preference('detailed', scope='global', identity='m2')
    assert unknown['scope_type'] == 'unknown'
    state = merge(unknown, global_record)
    assert len(state['preferences']) == 2
    assert not state['records_history']


def test_equal_timestamp_conflict_is_independent_of_input_order():
    records = [preference('concise', scope='global'), preference('detailed', scope='global', identity='m2')]
    for values in itertools.permutations(records):
        state = merge(*values)
        assert len(state['preferences']) == 2
        assert all(r['conflict'] for r in state['preferences'])
        assert not state['records_history']
        assert all(set(r['conflict_source_ids']) == {'m1', 'm2'} for r in state['preferences'])


@pytest.mark.parametrize('at', ['', 'not-a-date', '2026-01-01', '2026-01-01T10:00:00'])
def test_ambiguous_dates_do_not_silently_lose_to_dated_preference(at):
    state = merge(preference('concise', at=at, scope='global'),
                  preference('detailed', at='2026-02-01T10:00:00Z', scope='global', identity='m2'))
    assert {r['value'] for r in state['preferences']} == {'concise', 'detailed'}
    assert all(r.get('conflict') for r in state['preferences'])
    assert not state['records_history']


def test_timestamps_are_compared_as_instants_and_history_is_source_linked():
    # Lexicographic order would incorrectly choose the first observation.
    state = merge(preference('concise', at='2026-02-01T12:00:00+08:00', scope='global'),
                  preference('detailed', at='2026-02-01T05:00:00Z', scope='global', identity='m2'))
    assert [r['value'] for r in state['preferences']] == ['detailed']
    old = state['records_history'][0]
    assert old['value'] == 'concise' and old['source_ids'] == ['m1']
    assert old['temporal'] == 'historical' and old['original_category'] == 'preferences'
    assert old['superseded_by_source_ids'] == ['m2']
    assert not old.get('valid_until'), 'Observation time alone is not an exact validity endpoint'


def test_later_matching_value_resolves_tied_conflict_without_losing_support():
    state = merge(preference('concise', scope='global'), preference('detailed', scope='global', identity='m2'))
    newest = preference('concise', at='2026-02-01T10:00:00Z', scope='global', identity='m3')
    merge_records(state, 'preferences', [newest], DEFAULT_SETTINGS)
    assert len(state['preferences']) == 1
    current = state['preferences'][0]
    assert current['value'] == 'concise' and set(current['source_ids']) == {'m1', 'm3'}
    assert not current.get('conflict')
    assert state['records_history'][0]['value'] == 'detailed'
    assert state['records_history'][0]['superseded_by_source_ids'] == ['m3']


def test_legacy_state_can_be_merged_without_mutating_input_or_manual_metadata():
    legacy = preference('concise')
    legacy.pop('scope', None)
    legacy.pop('scope_type', None)
    legacy['manual_note'] = 'Keep the source quotation.'
    original = copy.deepcopy(legacy)
    state = {'preferences': [legacy]}
    merge_records(state, 'preferences', [preference('concise', identity='m2')], DEFAULT_SETTINGS)
    assert state['preferences'][0]['manual_note'] == original['manual_note']
    assert state['preferences'][0]['scope_type'] == 'unknown'
    assert len(state['preferences']) == 1


def test_only_actual_quoted_support_dates_determine_preference_chronology():
    quote = 'I prefer concise explanations.'
    session = {'messages': [
        {'id': 'm1', 'role': 'user', 'text': quote, 'timestamp': '2026-01-01T10:00:00Z'},
        {'id': 'context', 'role': 'user', 'text': 'Can you check the build?', 'timestamp': '2026-03-01T10:00:00Z'}]}
    raw = dict(key='communication.detail', value='concise', text=quote, domain='personal',
               kind='user_fact', scope='global', source_ids=['m1', 'context'], evidence=quote)
    old = validate_record(raw, session)
    assert old['observed_at'] == '2026-01-01T10:00:00Z'
    assert old['supporting_observations'] == [
        {'source_id': 'm1', 'evidence': quote, 'observed_at': '2026-01-01T10:00:00Z'}]
    state = merge(old, preference('detailed', at='2026-02-01T10:00:00Z', scope='global', identity='m2'))
    assert [r['value'] for r in state['preferences']] == ['detailed']
    assert state['records_history'][0]['source_ids'] == ['m1', 'context']


def test_support_dates_are_kept_individually_and_compared_as_instants():
    quote = 'I prefer concise explanations.'
    raw = dict(key='communication.detail', value='concise', text=quote, domain='personal',
               kind='user_fact', scope='global', source_ids=['m1', 'm2'], evidence=quote)
    session = {'messages': [
        {'id': 'm1', 'role': 'user', 'text': quote, 'timestamp': '2026-02-01T12:00:00+08:00'},
        {'id': 'm2', 'role': 'user', 'text': quote, 'timestamp': '2026-02-01T05:00:00Z'}]}
    record = validate_record(raw, session)
    assert record['observed_at'] == '2026-02-01T05:00:00Z'
    assert len(record['supporting_observations']) == 2


def test_known_and_undated_equivalent_support_cannot_erase_conflicting_statement():
    state = merge(preference('concise', at='', scope='global'),
                  preference('detailed', scope='global', identity='m2'),
                  preference('concise', at='2026-02-01T10:00:00Z', scope='global', identity='m3'))
    assert {r['value'] for r in state['preferences']} == {'concise', 'detailed'}
    assert all(r['conflict'] for r in state['preferences'])


def test_revision_cycle_retains_distinct_source_backed_stages_and_retry_is_idempotent():
    records = [preference('concise', scope='global'),
               preference('detailed', at='2026-02-01T10:00:00Z', scope='global', identity='m2'),
               preference('concise', at='2026-03-01T10:00:00Z', scope='global', identity='m3')]
    state = merge(*records)
    assert state['preferences'][0]['source_ids'] == ['m3']
    assert [(r['value'], r['source_ids']) for r in state['records_history']] == [
        ('concise', ['m1']), ('detailed', ['m2'])]
    snapshot = copy.deepcopy(state)
    merge_records(state, 'preferences', [records[-1]], DEFAULT_SETTINGS)
    assert state == snapshot


def test_late_middle_revision_reconstructs_the_same_three_stages_for_every_arrival_order():
    records = [preference('concise', scope='global'),
               preference('detailed', at='2026-02-01T10:00:00Z', scope='global', identity='m2'),
               preference('concise', at='2026-03-01T10:00:00Z', scope='global', identity='m3')]
    for order in itertools.permutations(records):
        state=merge(*order)
        assert [(r['value'],r['source_ids']) for r in state['preferences']]==[('concise',['m3'])]
        assert [(r['value'],r['source_ids']) for r in state['records_history']]==[
            ('concise',['m1']),('detailed',['m2'])]
