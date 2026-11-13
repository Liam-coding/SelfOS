"""Bounded, resumable native OpenCode scans and fresh original resolution."""
import copy
import json
import math
import re
import sqlite3
from pathlib import Path
from time import monotonic as _now

from selfos.sources.documents import SourceUnavailable
from selfos.sources.selection import validate_selection, allowed_database, project_allowed
from selfos.sources.opencode_records import PROFILE, _native_id, _absolute, _diagnostic
from selfos.sources.opencode_sqlite import (open_snapshot, probe_schema, session_metadata,
    session_proof, read_record, VALID_META)
from selfos.knowledge.identity import digest

DEFAULT_LIMITS = dict(deadline_seconds=10.0, busy_timeout_ms=250, sessions=100,
    messages=2000, page_size=100, parts=256, info_bytes=64*1024, part_bytes=256*1024,
    message_bytes=256*1024, text_bytes=8*1024*1024)
MAX_CHECKPOINT_BYTES = 8 * 1024 * 1024


def _limits(patch):
    if patch is None:
        return dict(DEFAULT_LIMITS)
    if not isinstance(patch, dict) or set(patch) - set(DEFAULT_LIMITS):
        raise SourceUnavailable('invalid_source_request', 'Invalid OpenCode scan limits')
    result = {**DEFAULT_LIMITS, **patch}
    for name, value in result.items():
        if name == 'deadline_seconds':
            valid = type(value) in (int, float) and math.isfinite(value)
        else:
            valid = type(value) is int
        if not valid or not 0 < value <= DEFAULT_LIMITS[name]:
            raise SourceUnavailable('invalid_source_request', 'Invalid OpenCode scan allowance')
    return result


def _parse_profile(limits):
    return digest({key: limits[key] for key in ('parts', 'info_bytes', 'part_bytes', 'message_bytes')})


def _key(value):
    if value is None:
        return
    if (not isinstance(value, list) or len(value) != 2 or type(value[0]) not in (int, float)
            or not math.isfinite(value[0]) or not 0 <= value[0] <= 253402300799999):
        raise ValueError('Invalid OpenCode ordered cursor')
    _native_id(value[1])


def _hash(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _advance(state, entry, **positions):
    """Reserve checkpoint space before exposing text or consuming an ordered row."""
    candidate = {**state, **positions, 'prefix': [*state['prefix'], entry]}
    if len(json.dumps(candidate).encode('utf-8')) > MAX_CHECKPOINT_BYTES:
        raise SourceUnavailable('bounded_read', 'OpenCode checkpoint exceeds staging allowance')
    state.update(candidate)


def _validate_cursor(value, path, selection, limits):
    if value is None:
        return
    keys = {'version', 'profile', 'path', 'selection_hash', 'parse_profile', 'schema',
            'session_water', 'message_water', 'session_after', 'active_session', 'message_after', 'prefix'}
    if (not isinstance(value, dict) or set(value) != keys or type(value['version']) is not int
            or value['version'] != 1 or value['profile'] != PROFILE or value['path'] != str(path)
            or value['selection_hash'] != digest(selection) or value['parse_profile'] != _parse_profile(limits)
            or not _hash(value['schema'])
            or not isinstance(value['prefix'], list)):
        raise ValueError('Invalid or stale OpenCode scan cursor')
    for name in ('session_water', 'message_water', 'session_after', 'active_session', 'message_after'):
        _key(value[name])
    if value['message_after'] is not None and value['active_session'] is None:
        raise ValueError('OpenCode message cursor has no session')
    for position, water in (('session_after', 'session_water'), ('active_session', 'session_water'),
                            ('message_after', 'message_water')):
        if value[position] is not None and (value[water] is None or value[position] > value[water]):
            raise ValueError('OpenCode cursor exceeds snapshot high-water')
    if (value['active_session'] is not None and value['session_after'] is not None
            and value['active_session'] <= value['session_after']):
        raise ValueError('OpenCode active session precedes completed input')
    if len(json.dumps(value).encode('utf-8')) > MAX_CHECKPOINT_BYTES:
        raise ValueError('OpenCode scan checkpoint exceeds memory limit')
    for entry in value['prefix']:
        if (not isinstance(entry, dict) or entry.get('kind') not in ('session', 'message')
                or set(entry) != ({'kind', 'id', 'time', 'proof'} if entry.get('kind') == 'session'
                                  else {'kind', 'id', 'session_id', 'time', 'proof'})
                or not _hash(entry['proof'])):
            raise ValueError('Invalid OpenCode consumed prefix')
        _key([entry['time'], entry['id']])
        if entry['kind'] == 'message':
            _native_id(entry['session_id'])


def _water(connection, table):
    row = connection.execute('SELECT time_created,id FROM ' + table + ' WHERE ' + VALID_META
        + ' ORDER BY time_created DESC,id DESC LIMIT 1').fetchone()
    return [row['time_created'], row['id']] if row else None


def _window(water, after):
    if water is None:
        return '0', []
    sql = '(time_created<? OR (time_created=? AND id<=?))'
    args = [water[0], water[0], water[1]]
    if after is not None:
        sql += ' AND (time_created>? OR (time_created=? AND id>?))'
        args.extend([after[0], after[0], after[1]])
    return sql, args


def _sessions(connection, state, maximum):
    clause, args = _window(state['session_water'], state['session_after'])
    return connection.execute('SELECT time_created,id FROM session WHERE ' + VALID_META + ' AND ' + clause
        + ' ORDER BY time_created,id LIMIT ?', [*args, maximum]).fetchall()


def _session_proof_entry(raw):
    return dict(kind='session', id=raw['id'], time=raw['row_time'], proof=session_proof(raw))


def _verify_prefix(connection, state, selection, limits, check):
    cache = {}
    for entry in state['prefix']:
        check()
        identity = entry['id'] if entry['kind'] == 'session' else entry['session_id']
        if identity not in cache:
            cache[identity] = session_metadata(connection, identity, validate=False)
        raw = cache[identity]
        if entry['kind'] == 'session':
            actual = _session_proof_entry(raw)
        else:
            session = session_metadata(connection, identity)
            if not project_allowed(session['directory'], selection):
                raise SourceUnavailable('source_denied', 'OpenCode project is excluded')
            _, proof, timestamp = read_record(connection, session, entry['id'],
                {'kind': 'database', 'path': state['path']}, limits, check, [])
            actual = dict(kind='message', id=entry['id'], session_id=identity, time=timestamp, proof=proof)
        if actual != entry:
            raise SourceUnavailable('source_changed', 'OpenCode consumed input changed; restart the scan')


def _result(status, messages, cursor, diagnostics, snapshot=None):
    return dict(status=status, messages=messages, cursor=cursor, diagnostics=diagnostics,
                snapshot=snapshot, partial=status != 'complete')


def _error_code(error, check):
    if isinstance(error, SourceUnavailable):
        return error.code
    if isinstance(error, sqlite3.OperationalError):
        try:
            check()
        except SourceUnavailable as interrupted:
            return interrupted.code
        if 'locked' in str(error).lower() or 'busy' in str(error).lower():
            return 'source_locked'
    if isinstance(error, sqlite3.DatabaseError):
        return 'unsupported_source_format'
    return 'source_unavailable'


def scan_database(path, selection, *, cursor=None, cancel=lambda: False, limits=None):
    diagnostics, messages, state = [], [], None
    deadline = None
    def check():
        if cancel():
            raise SourceUnavailable('stopped', 'OpenCode scan stopped')
        if deadline is not None and _now() >= deadline:
            raise SourceUnavailable('bounded_read', 'OpenCode scan deadline reached')
    try:
        limits = _limits(limits)
        path = Path(_absolute(str(path)))
        selection = validate_selection(selection)
        try:
            _validate_cursor(cursor, path, selection, limits)
        except (ValueError, TypeError, KeyError):
            return _result('invalid_source_request', [], cursor, [{'code': 'invalid_source_request'}])
        if not allowed_database(path, selection):
            raise SourceUnavailable('source_denied', 'OpenCode database is not explicitly selected')
        if not path.is_file():
            raise SourceUnavailable('source_missing', 'OpenCode database is missing')
        deadline = _now() + limits['deadline_seconds']
        check()
        with open_snapshot(path, limits, check) as connection:
            schema = probe_schema(connection, check)
            if cursor is None:
                state = dict(version=1, profile=PROFILE, path=str(path), selection_hash=digest(selection),
                    parse_profile=_parse_profile(limits), schema=schema,
                    session_water=_water(connection, 'session'), message_water=_water(connection, 'message'),
                    session_after=None, active_session=None, message_after=None, prefix=[])
            else:
                if cursor['schema'] != schema:
                    raise SourceUnavailable('source_changed', 'OpenCode schema changed; restart the scan')
                state = copy.deepcopy(cursor)
                _verify_prefix(connection, state, selection, limits, check)
            processed, entered, payload = 0, 0, 0
            while True:
                check()
                if len(json.dumps(state).encode('utf-8')) > MAX_CHECKPOINT_BYTES:
                    raise SourceUnavailable('bounded_read', 'OpenCode checkpoint exceeds staging allowance')
                if state['active_session'] is None:
                    rows = _sessions(connection, state, 1)
                    if not rows:
                        return _result('complete', messages, None, diagnostics, state)
                    if entered >= limits['sessions'] or processed >= limits['messages']:
                        return _result('partial', messages, state, diagnostics, state)
                    raw = session_metadata(connection, rows[0]['id'], validate=False)
                    _advance(state, _session_proof_entry(raw),
                        active_session=[rows[0]['time_created'], rows[0]['id']], message_after=None)
                    entered += 1
                try:
                    session = session_metadata(connection, state['active_session'][1])
                except ValueError:
                    _diagnostic(diagnostics, 'invalid_record')
                    state['session_after'], state['active_session'], state['message_after'] = state['active_session'], None, None
                    continue
                if not project_allowed(session['directory'], selection):
                    _diagnostic(diagnostics, 'project_excluded')
                    state['session_after'], state['active_session'], state['message_after'] = state['active_session'], None, None
                    continue
                clause, args = _window(state['message_water'], state['message_after'])
                rows = connection.execute('SELECT time_created,id FROM message WHERE session_id=? AND '
                    + VALID_META + ' AND ' + clause + ' ORDER BY time_created,id LIMIT ?',
                    [session['id'], *args, limits['page_size'] + 1]).fetchall()
                if not rows:
                    state['session_after'], state['active_session'], state['message_after'] = state['active_session'], None, None
                    continue
                for row in rows[:limits['page_size']]:
                    check()
                    if processed >= limits['messages']:
                        return _result('partial', messages, state, diagnostics, state)
                    message, proof, timestamp = read_record(connection, session, row['id'],
                        {'kind': 'database', 'path': str(path)}, limits, check, diagnostics)
                    size = len(json.dumps(message, ensure_ascii=False).encode('utf-8')) if message else 0
                    if payload + size > limits['text_bytes']:
                        return _result('partial', messages, state, diagnostics, state)
                    _advance(state, dict(kind='message', id=row['id'], session_id=session['id'], time=timestamp, proof=proof),
                        message_after=[row['time_created'], row['id']])
                    if message:
                        messages.append(message)
                        payload += size
                    processed += 1
                if len(rows) <= limits['page_size']:
                    state['session_after'], state['active_session'], state['message_after'] = state['active_session'], None, None
    except (SourceUnavailable, sqlite3.Error, OSError, ValueError, TypeError) as error:
        code = _error_code(error, check)
        _diagnostic(diagnostics, code)
        if code in ('stopped', 'bounded_read') and state is not None:
            return _result(code, messages, state, diagnostics, state)
        return _result(code, [], cursor, diagnostics)


def resolve_database(locator, selection):
    """Verify exact native linkage, included parts, text and semantic source identity."""
    keys = {'kind', 'path', 'version', 'profile', 'project_id', 'session_id', 'message_id',
            'part_ids', 'text_sha256', 'source_id'}
    if (not isinstance(locator, dict) or set(locator) != keys or locator.get('kind') != 'database'
            or locator.get('profile') != PROFILE or locator.get('version') != 1):
        raise SourceUnavailable('invalid_source_request', 'Invalid native source locator')
    try:
        for key in ('project_id', 'session_id', 'message_id'):
            _native_id(locator[key])
        if (not isinstance(locator['part_ids'], list) or not 1 <= len(locator['part_ids']) <= 256
                or len({_native_id(value) for value in locator['part_ids']}) != len(locator['part_ids'])
                or any(not isinstance(locator[key], str) or len(locator[key]) != 64 for key in ('source_id', 'text_sha256'))):
            raise ValueError('Invalid native source identity')
        path = Path(_absolute(locator['path']))
        selection = validate_selection(selection)
    except (ValueError, TypeError):
        raise SourceUnavailable('invalid_source_request', 'Invalid native source identity') from None
    if not allowed_database(path, selection):
        raise SourceUnavailable('source_denied', 'Native database is not explicitly selected')
    if not path.is_file():
        raise SourceUnavailable('source_missing', 'Native database is missing')
    deadline = _now() + DEFAULT_LIMITS['deadline_seconds']
    def check():
        if _now() >= deadline:
            raise SourceUnavailable('bounded_read', 'Native source deadline reached')
    try:
        with open_snapshot(path, DEFAULT_LIMITS, check) as connection:
            probe_schema(connection, check)
            session = session_metadata(connection, locator['session_id'])
            if session['projectID'] != locator['project_id']:
                raise SourceUnavailable('source_changed', 'Native project linkage changed')
            if not project_allowed(session['directory'], selection):
                raise SourceUnavailable('source_denied', 'Native project is excluded')
            message, _, _ = read_record(connection, session, locator['message_id'],
                {'kind': 'database', 'path': str(path)}, DEFAULT_LIMITS, check, [])
            if (message is None or message['id'] != locator['source_id']
                    or message['source_locator']['part_ids'] != locator['part_ids']
                    or message['source_locator']['text_sha256'] != locator['text_sha256']):
                raise SourceUnavailable('source_changed', 'Native source changed')
            return message
    except (sqlite3.Error, OSError) as error:
        raise SourceUnavailable(_error_code(error, check), 'Native source cannot be verified') from None
    except ValueError as error:
        if isinstance(error, SourceUnavailable):
            raise
        raise SourceUnavailable('source_changed', 'Native source metadata changed') from None
