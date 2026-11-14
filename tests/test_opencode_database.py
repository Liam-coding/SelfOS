"""Synthetic pinned SQLite projection; no upstream invocation or real transcripts."""
import copy
import hashlib
import json
import sqlite3

import pytest

from selfos.sources.selection import validate_selection


def create_database(tmp_path, count=5, *, wal=False, directory=None):
    path = tmp_path / 'native.db'
    connection = sqlite3.connect(path)
    if wal:
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA wal_autocheckpoint=0')
    connection.executescript('''
        CREATE TABLE session(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, directory TEXT, time_created INTEGER NOT NULL);
        CREATE TABLE message(id TEXT PRIMARY KEY, session_id TEXT NOT NULL, time_created INTEGER NOT NULL, data TEXT NOT NULL);
        CREATE TABLE part(id TEXT PRIMARY KEY, message_id TEXT NOT NULL, session_id TEXT NOT NULL, time_created INTEGER NOT NULL, data TEXT NOT NULL);
        CREATE INDEX message_session_time ON message(session_id,time_created,id);
        CREATE INDEX part_message_id ON part(message_id,id);
    ''')
    connection.execute('INSERT INTO session VALUES (?,?,?,?)',
        ('ses_synthetic', 'project_synthetic', str(directory or tmp_path / 'project'), 1700000000000))
    for index in range(count):
        add_message(connection, index)
    connection.commit()
    selected = validate_selection({'version': 2, 'entries': [{'kind': 'opencode_database', 'path': str(path)}]})
    if not wal:
        connection.close()
        connection = None
    return path, selected, connection


def add_message(connection, index, *, created=1700000000123, role='user'):
    message_id = f'msg_{index:04d}'
    info = {'role': role, 'time': {'created': created}}
    connection.execute('INSERT INTO message VALUES (?,?,?,?)',
        (message_id, 'ses_synthetic', created, json.dumps(info)))
    for suffix, text in [('b', 'Keep immutable originals and backups.'), ('a', f'Synthetic project decision {index}.')]:
        connection.execute('INSERT INTO part VALUES (?,?,?,?,?)',
            (f'prt_{index:04d}_{suffix}', message_id, 'ses_synthetic', created,
             json.dumps({'type': 'text', 'text': text})))


def test_native_scan_uses_read_only_uri_and_preserves_content_and_schema(tmp_path, monkeypatch):
    from selfos.sources import opencode_database as native
    path, selection, _ = create_database(tmp_path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    real_connect = sqlite3.connect
    calls = []
    def connect(value, *args, **kwargs):
        calls.append((value, kwargs))
        return real_connect(value, *args, **kwargs)
    monkeypatch.setattr(native.sqlite3, 'connect', connect)
    result = native.scan_database(path, selection)
    assert result['status'] == 'complete' and not result['partial']
    assert len(result['messages']) == 5
    assert all(message['source'] == 'opencode' for message in result['messages'])
    assert calls and all('mode=ro' in value and kwargs.get('uri') is True for value, kwargs in calls)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_read_only_scan_sees_committed_wal_rows_without_main_database_mutation(tmp_path):
    from selfos.sources.opencode_database import scan_database
    path, selection, writer = create_database(tmp_path, count=0, wal=True)
    try:
        add_message(writer, 0)
        writer.commit()
        before = path.read_bytes()
        assert scan_database(path, selection)['messages'][0]['native_message_id'] == 'msg_0000'
        assert path.read_bytes() == before
    finally:
        writer.close()


@pytest.mark.parametrize('schema', ['unknown', 'v2_only', 'wrong_type'])
def test_unsupported_projection_is_explicit_not_empty_success(tmp_path, schema):
    from selfos.sources.opencode_database import scan_database
    if schema == 'wrong_type':
        path, selection, _ = create_database(tmp_path)
        with sqlite3.connect(path) as connection:
            connection.execute('ALTER TABLE message RENAME TO old_message')
            connection.execute('CREATE TABLE message(id TEXT,session_id TEXT,time_created TEXT,data TEXT)')
    else:
        path = tmp_path / 'native.db'
        with sqlite3.connect(path) as connection:
            connection.execute('CREATE TABLE session_message(id TEXT,data TEXT)' if schema == 'v2_only'
                               else 'CREATE TABLE arbitrary(id TEXT,data TEXT)')
        selection = validate_selection({'version': 2, 'entries': [{'kind': 'opencode_database', 'path': str(path)}]})
    result = scan_database(path, selection)
    assert result['status'] == 'unsupported_source_format' and not result['messages']
    assert result['diagnostics']


def test_additive_columns_do_not_invalidate_the_pinned_projection(tmp_path):
    from selfos.sources.opencode_database import scan_database
    path, selection, _ = create_database(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute('ALTER TABLE message ADD COLUMN extra_metadata TEXT')
    assert scan_database(path, selection)['status'] == 'complete'


def test_same_time_keyset_pages_resume_without_duplicates_and_ignore_new_high_water_rows(tmp_path):
    from selfos.sources.opencode_database import scan_database
    path, selection, _ = create_database(tmp_path)
    result = scan_database(path, selection, limits={'messages': 2, 'page_size': 1})
    assert result['partial'] and result['cursor']
    seen = result['messages']
    with sqlite3.connect(path) as connection:
        add_message(connection, 99, created=1700000010000)
    for _ in range(4):
        result = scan_database(path, selection, cursor=result['cursor'], limits={'messages': 2, 'page_size': 1})
        seen.extend(result['messages'])
        if not result['partial']:
            break
    assert [message['native_message_id'] for message in seen] == [f'msg_{index:04d}' for index in range(5)]
    assert len({message['id'] for message in seen}) == 5
    assert not result['partial'] and result['status'] == 'complete'
    assert len(scan_database(path, selection)['messages']) == 6


def test_changed_consumed_prefix_requires_restart_and_preserves_cursor(tmp_path):
    from selfos.sources.opencode_database import scan_database
    path, selection, _ = create_database(tmp_path)
    first = scan_database(path, selection, limits={'messages': 2})
    with sqlite3.connect(path) as connection:
        connection.execute('UPDATE part SET data=? WHERE id=?',
            (json.dumps({'type': 'text', 'text': 'Changed durable project decision.'}), 'prt_0000_a'))
    result = scan_database(path, selection, cursor=first['cursor'])
    assert result['status'] == 'source_changed' and not result['messages']
    assert result['cursor'] == first['cursor'] and result['partial']


def test_excluded_project_is_filtered_before_message_or_part_bodies_are_read(tmp_path, monkeypatch):
    from selfos.sources import opencode_database as native
    private = tmp_path / 'private-project'
    path, selection, _ = create_database(tmp_path, directory=private)
    selection['project_exclusions'] = [str(private)]
    statements = []
    real_connect = sqlite3.connect
    def connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection
    monkeypatch.setattr(native.sqlite3, 'connect', connect)
    result = native.scan_database(path, selection)
    assert not result['messages']
    assert any(row['code'] == 'project_excluded' for row in result['diagnostics'])
    assert not any('data' in query.lower() and ('from message' in query.lower() or 'from part' in query.lower())
                   for query in statements)


@pytest.mark.parametrize('kind', ['info', 'part', 'foreign_part', 'invalid_role'])
def test_invalid_or_oversize_records_are_diagnosed_without_false_complete_sources(tmp_path, kind):
    from selfos.sources.opencode_database import scan_database
    path, selection, _ = create_database(tmp_path, count=1)
    with sqlite3.connect(path) as connection:
        if kind == 'info':
            connection.execute('UPDATE message SET data=?', (json.dumps({'extra': 'X' * 70000}),))
        elif kind == 'part':
            connection.execute('UPDATE part SET data=? WHERE id=?',
                (json.dumps({'type': 'text', 'text': 'X' * 300000}), 'prt_0000_a'))
        elif kind == 'foreign_part':
            connection.execute('UPDATE part SET session_id=? WHERE id=?', ('ses_other', 'prt_0000_a'))
        else:
            connection.execute('UPDATE message SET data=?',
                (json.dumps({'role': 'system', 'time': {'created': 1700000000123}}),))
    result = scan_database(path, selection)
    assert not result['messages'] and result['diagnostics']
    assert any(row['code'] in ('oversize_record', 'invalid_record') for row in result['diagnostics'])


def test_cancellation_does_not_open_storage_or_complete_unread_work(tmp_path, monkeypatch):
    from selfos.sources import opencode_database as native
    path, selection, _ = create_database(tmp_path)
    monkeypatch.setattr(native.sqlite3, 'connect', lambda *args, **kwargs: pytest.fail('Cancelled scan must not open storage'))
    result = native.scan_database(path, selection, cancel=lambda: True)
    assert result['status'] == 'stopped' and result['partial'] and not result['messages']


def test_scan_deadline_is_explicit_and_leaves_unread_work_pending(tmp_path, monkeypatch):
    from selfos.sources import opencode_database as native
    path, selection, _ = create_database(tmp_path)
    ticks = iter([0.0, 100.0])
    monkeypatch.setattr(native, '_now', lambda: next(ticks, 100.0))
    result = native.scan_database(path, selection, limits={'deadline_seconds': 0.01})
    assert result['status'] == 'bounded_read' and result['partial'] and not result['messages']


def test_locked_database_is_reported_without_initialization(tmp_path):
    from selfos.sources.opencode_database import scan_database
    path, selection, _ = create_database(tmp_path)
    writer = sqlite3.connect(path)
    try:
        writer.execute('BEGIN EXCLUSIVE')
        result = scan_database(path, selection, limits={'busy_timeout_ms': 10})
        assert result['status'] == 'source_locked' and not result['messages']
    finally:
        writer.rollback()
        writer.close()


@pytest.mark.parametrize('change', ['text', 'role', 'time', 'part_ids', 'project'])
def test_original_resolution_rechecks_semantics_and_native_linkage(tmp_path, change):
    from selfos.sources.opencode_database import scan_database, resolve_database
    path, selection, _ = create_database(tmp_path, count=1)
    message = scan_database(path, selection)['messages'][0]
    locator = message['source_locator']
    assert resolve_database(locator, selection)['id'] == message['id']
    with sqlite3.connect(path) as connection:
        if change == 'text':
            connection.execute('UPDATE part SET data=? WHERE id=?', (json.dumps({'type': 'text', 'text': 'Changed context.'}), 'prt_0000_a'))
        elif change == 'role':
            connection.execute('UPDATE message SET data=?', (json.dumps({'role': 'assistant', 'time': {'created': 1700000000123}}),))
        elif change == 'time':
            connection.execute('UPDATE message SET data=?', (json.dumps({'role': 'user', 'time': {'created': 1700000000124}}),))
        elif change == 'part_ids':
            connection.execute('UPDATE part SET id=? WHERE id=?', ('prt_replaced', 'prt_0000_a'))
        else:
            connection.execute('UPDATE session SET project_id=?', ('project_other',))
    with pytest.raises(ValueError) as error:
        resolve_database(locator, selection)
    assert error.value.code == 'source_changed'


def test_unrelated_new_messages_do_not_invalidate_an_existing_source(tmp_path):
    from selfos.sources.opencode_database import scan_database, resolve_database
    path, selection, _ = create_database(tmp_path, count=1)
    original = scan_database(path, selection)['messages'][0]
    with sqlite3.connect(path) as connection:
        add_message(connection, 1, created=1700000020000)
    assert resolve_database(original['source_locator'], selection)['id'] == original['id']


def test_forged_cursor_does_not_grant_storage_permission(tmp_path, monkeypatch):
    from selfos.sources import opencode_database as native
    path, selection, _ = create_database(tmp_path)
    monkeypatch.setattr(native.sqlite3, 'connect', lambda *args, **kwargs: pytest.fail('Invalid cursor must be rejected before opening'))
    result = native.scan_database(path, selection, cursor={'version': 1, 'path': str(tmp_path / 'unselected.db')})
    assert result['status'] == 'invalid_source_request' and not result['messages']


def test_checkpoint_cap_never_returns_oversize_state_or_advances_unretained_message(tmp_path, monkeypatch):
    from selfos.sources import opencode_database as native
    path, selection, _ = create_database(tmp_path)
    first = native.scan_database(path, selection, limits={'messages': 1})
    cap = len(json.dumps(first['cursor']).encode('utf-8')) + 1
    monkeypatch.setattr(native, 'MAX_CHECKPOINT_BYTES', cap)
    result = native.scan_database(path, selection)
    assert result['status'] == 'bounded_read'
    assert len(json.dumps(result['cursor']).encode('utf-8')) <= cap
    assert [message['native_message_id'] for message in result['messages']] == ['msg_0000']
    assert result['cursor']['message_after'][1] == 'msg_0000'


@pytest.mark.parametrize('change', ['non_hex_proof', 'after_water'])
def test_cursor_validation_rejects_bad_proofs_and_out_of_window_positions(tmp_path, monkeypatch, change):
    from selfos.sources import opencode_database as native
    path, selection, _ = create_database(tmp_path)
    first = native.scan_database(path, selection, limits={'messages': 1})
    cursor = copy.deepcopy(first['cursor'])
    if change == 'non_hex_proof':
        cursor['prefix'][0]['proof'] = 'Z' * 64
    else:
        cursor['message_after'] = [cursor['message_water'][0] + 1, 'msg_future']
    monkeypatch.setattr(native.sqlite3, 'connect', lambda *args, **kwargs: pytest.fail('Invalid cursor must not open storage'))
    result = native.scan_database(path, selection, cursor=cursor)
    assert result['status'] == 'invalid_source_request'
