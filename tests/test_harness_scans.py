"""Only synthetic databases and temporary vaults are used."""
import json
import sqlite3

import pytest

from test_opencode_database import create_database, add_message
from selfos.sources.selection import save_sources
from selfos.sources.compaction import prepare_sessions


def setup_scan(tmp_path, count=5):
    path, selection, _ = create_database(tmp_path, count=count)
    vault = tmp_path / 'vault'
    vault.mkdir()
    save_sources(vault, selection)
    return vault, path, selection['entries'][0], selection


def test_durable_paged_scan_matches_full_session_and_cache_keys(tmp_path):
    from selfos.storage.harness_scans import advance_scan, acknowledge_scan
    from selfos.sources.opencode_database import scan_database
    vault, path, entry, selection = setup_scan(tmp_path)
    expected = prepare_sessions(scan_database(path, selection)['messages'], max_chars=60)
    actual = []
    for _ in range(10):
        result = advance_scan(vault, entry, limits={'messages': 2}, max_chars=60)
        actual.extend(result['sealed_sessions'])
        if result['sealed_sessions']:
            acknowledge_scan(vault, entry, result['sealed_ids'], max_chars=60)
        if result['status'] == 'complete':
            break
    assert actual == expected
    assert result['status'] == 'complete'
    assert not advance_scan(vault, entry, max_chars=60)['sealed_sessions']


def test_pending_sealed_parts_are_replayed_before_scanning_new_pages(tmp_path, monkeypatch):
    from selfos.storage import harness_scans as scans
    vault, path, entry, _ = setup_scan(tmp_path, count=1)
    first = scans.advance_scan(vault, entry, max_chars=30)
    assert first['sealed_sessions']
    def unexpected(*args, **kwargs):
        pytest.fail('Pending inputs must be returned before advancing a database page')
    monkeypatch.setattr(scans, 'scan_database', unexpected)
    assert scans.advance_scan(vault, entry, max_chars=30) == first


@pytest.mark.parametrize('after_replace', [False, True])
def test_failed_checkpoint_publication_never_loses_or_duplicates_input(tmp_path, monkeypatch, after_replace):
    from selfos.storage import harness_scans as scans
    vault, path, entry, _ = setup_scan(tmp_path, count=1)
    real = scans._atomic_write
    def failed(path, raw):
        if after_replace:
            real(path, raw)
        raise OSError('Synthetic crash at publication boundary')
    monkeypatch.setattr(scans, '_atomic_write', failed)
    with pytest.raises(OSError):
        scans.advance_scan(vault, entry, max_chars=30)
    monkeypatch.setattr(scans, '_atomic_write', real)
    recovered = scans.advance_scan(vault, entry, max_chars=30)
    assert recovered['status'] == 'complete'
    assert [part['part'] for part in recovered['sealed_sessions']] == list(range(len(recovered['sealed_sessions'])))


def test_changed_consumed_input_keeps_durable_checkpoint_unchanged(tmp_path):
    from selfos.storage.harness_scans import advance_scan
    vault, path, entry, _ = setup_scan(tmp_path)
    first = advance_scan(vault, entry, limits={'messages': 1})
    assert not first['sealed_sessions']
    state_path = next((vault / '.knowledge_harness_scans').glob('*.json'))
    before = state_path.read_bytes()
    with sqlite3.connect(path) as connection:
        connection.execute('UPDATE part SET data=? WHERE id=?',
            (json.dumps({'type': 'text', 'text': 'Changed durable project goal.'}), 'prt_0000_a'))
    result = advance_scan(vault, entry)
    assert result['status'] == 'source_changed'
    assert state_path.read_bytes() == before


@pytest.mark.parametrize('cap', ['page', 'snapshot', 'aggregate'])
def test_staging_caps_leave_unpublished_cursor_pending(tmp_path, monkeypatch, cap):
    from selfos.storage import harness_scans as scans
    vault, path, entry, _ = setup_scan(tmp_path)
    monkeypatch.setattr(scans, {'page': 'MAX_PAGE_BYTES', 'snapshot': 'MAX_SNAPSHOT_BYTES',
                               'aggregate': 'MAX_AGGREGATE_BYTES'}[cap], 1)
    result = scans.advance_scan(vault, entry)
    assert result['status'] == 'staging_limit' and not result['sealed_sessions']
    assert not list((vault / '.knowledge_harness_scans').glob('*.json'))


def test_corrupt_checkpoint_is_not_silently_restarted(tmp_path):
    from selfos.storage.harness_scans import advance_scan
    vault, path, entry, _ = setup_scan(tmp_path)
    advance_scan(vault, entry, limits={'messages': 1})
    state_path = next((vault / '.knowledge_harness_scans').glob('*.json'))
    state_path.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError):
        advance_scan(vault, entry)
    assert state_path.read_text() == '{}'


def test_high_water_snapshot_does_not_absorb_later_new_messages(tmp_path):
    from selfos.storage.harness_scans import advance_scan
    vault, path, entry, _ = setup_scan(tmp_path)
    first = advance_scan(vault, entry, limits={'messages': 1})
    with sqlite3.connect(path) as connection:
        add_message(connection, 99, created=1700000020000)
    result = advance_scan(vault, entry)
    assert result['status'] == 'complete'
    assert len({message['native_message_id'] for part in result['sealed_sessions'] for message in part['messages']}) == 5


def test_stop_before_read_preserves_unsealed_input(tmp_path):
    from selfos.storage.harness_scans import advance_scan
    vault, path, entry, _ = setup_scan(tmp_path)
    first = advance_scan(vault, entry, limits={'messages': 1})
    assert not first['sealed_sessions']
    state_path = next((vault / '.knowledge_harness_scans').glob('*.json'))
    before = state_path.read_bytes()
    assert advance_scan(vault, entry, cancel=lambda: True)['status'] == 'stopped'
    assert state_path.read_bytes() == before
    assert advance_scan(vault, entry)['sealed_sessions']


def test_identical_slices_have_distinct_acknowledgement_ids(tmp_path):
    from selfos.storage.harness_scans import advance_scan, acknowledge_scan
    vault, path, entry, _ = setup_scan(tmp_path, count=1)
    with sqlite3.connect(path) as connection:
        connection.execute('DELETE FROM part WHERE id=?', ('prt_0000_b',))
        connection.execute('UPDATE part SET data=? WHERE id=?',
            (json.dumps({'type': 'text', 'text': 'Durable decision. ' * 12}), 'prt_0000_a'))
    result = advance_scan(vault, entry, max_chars=18)
    assert len(result['sealed_ids']) == len(set(result['sealed_ids'])) == len(result['sealed_sessions'])
    first_id = result['sealed_ids'][0]
    remaining = acknowledge_scan(vault, entry, [first_id], max_chars=18)
    assert len(remaining['sealed_ids']) == len(result['sealed_ids']) - 1
    assert first_id not in remaining['sealed_ids']
