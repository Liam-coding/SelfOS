"""Paged packing preserves existing model inputs and cache fingerprints."""
import copy
import json

import pytest

from selfos.sources.compaction import prepare_sessions


def record(identity, timestamp, text):
    return dict(id=identity, timestamp=timestamp, text=text, role='user',
                project_id='synthetic-project', session_id='synthetic-session')


@pytest.mark.parametrize('page_size', [1, 2, 3, 7])
def test_paged_compaction_matches_full_packing_including_same_time_id_order(page_size):
    from selfos.sources.resumable_compaction import resume_compaction
    messages = [record(identity, timestamp, text) for identity, timestamp, text in [
        ('z', '2026-01-01T00:00:00Z', 'Use immutable originals for evidence.'),
        ('a', '2026-01-01T00:00:00Z', 'Preserve source links and backups.'),
        ('m', '2026-01-01T00:00:01Z', 'Long project decision. ' * 10),
        ('c', '2026-01-01T00:00:02Z', 'Keep each project separated.'),
        ('q', '2026-01-01T00:00:03Z', 'Continue tracking durable project state.'),
    ]]
    carry, sealed = None, []
    for start in range(0, len(messages), page_size):
        result = resume_compaction(messages[start:start+page_size], carry,
            session_end=start+page_size >= len(messages), max_chars=55)
        sealed.extend(result['sealed'])
        carry = json.loads(json.dumps(result['carry'])) if result['carry'] else None
    assert sealed == prepare_sessions(messages, max_chars=55)
    assert carry is None
    assert result['next_part'] == len(sealed)


def test_unfinished_tied_timestamp_is_not_prematurely_sealed_or_reordered():
    from selfos.sources.resumable_compaction import resume_compaction
    first = record('z', '2026-01-01T00:00:00Z', 'Keep durable project evidence. ' * 6)
    result = resume_compaction([first], None, session_end=False, max_chars=40)
    assert not result['sealed'] and result['carry']
    original = copy.deepcopy(result['carry'])
    second = record('a', first['timestamp'], 'Prefer independent provenance verification.')
    final = resume_compaction([second], result['carry'], session_end=True, max_chars=40)
    assert result['carry'] == original
    assert final['sealed'] == prepare_sessions([first, second], max_chars=40)


def test_stopped_empty_page_preserves_carry_and_final_flush_seals_exactly_once():
    from selfos.sources.resumable_compaction import resume_compaction
    messages = [record('a', '2026-01-01T00:00:00Z', 'Track long term project goals.')]
    start = resume_compaction(messages, None, session_end=False, max_chars=100)
    stopped = resume_compaction([], start['carry'], session_end=False, max_chars=100)
    assert stopped == start
    final = resume_compaction([], stopped['carry'], session_end=True, max_chars=100)
    assert final['sealed'] == prepare_sessions(messages, max_chars=100)
    assert final['carry'] is None


@pytest.mark.parametrize('fault', ['backwards_time', 'other_session', 'changed_size', 'corrupt_carry'])
def test_rejects_incompatible_resume_without_mutating_checkpoint(fault):
    from selfos.sources.resumable_compaction import resume_compaction
    start = resume_compaction([record('a', '2026-01-01T00:00:01Z', 'Keep durable evidence.')],
                              None, session_end=False, max_chars=100)
    carry = copy.deepcopy(start['carry'])
    message = record('b', '2026-01-01T00:00:02Z', 'Retain provenance for each fact.')
    size = 100
    if fault == 'backwards_time':
        message['timestamp'] = '2026-01-01T00:00:00Z'
    elif fault == 'other_session':
        message['session_id'] = 'other-session'
    elif fault == 'changed_size':
        size = 99
    else:
        carry['next_part'] = -1
    before = copy.deepcopy(carry)
    with pytest.raises(ValueError):
        resume_compaction([message], carry, session_end=False, max_chars=size)
    assert carry == before
