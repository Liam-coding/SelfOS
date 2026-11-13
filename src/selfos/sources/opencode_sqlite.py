"""Read-only pinned SQLite lifecycle and bounded record hydration."""
from contextlib import contextmanager
import json
import sqlite3

from selfos.sources.documents import SourceUnavailable
from selfos.sources.opencode_records import normalize_record, _native_id, _absolute, _diagnostic
from selfos.sources.text import redact
from selfos.knowledge.identity import digest

REQUIRED = {
    'session': {'id': 'TEXT', 'project_id': 'TEXT', 'directory': 'TEXT', 'time_created': 'INTEGER'},
    'message': {'id': 'TEXT', 'session_id': 'TEXT', 'time_created': 'INTEGER', 'data': 'TEXT'},
    'part': {'id': 'TEXT', 'message_id': 'TEXT', 'session_id': 'TEXT', 'time_created': 'INTEGER', 'data': 'TEXT'},
}
VALID_META = ("typeof(time_created) IN ('integer','real') AND time_created>=0 AND time_created<=253402300799999 "
              "AND typeof(id)='text' AND length(id) BETWEEN 1 AND 200 "
              "AND substr(id,1,1) GLOB '[A-Za-z0-9]' AND id NOT GLOB '*[^A-Za-z0-9._:-]*'")


def _authorize(action, first, second, database, trigger):
    if action == sqlite3.SQLITE_READ:
        return sqlite3.SQLITE_OK if first in (*REQUIRED, 'sqlite_master', 'sqlite_schema') else sqlite3.SQLITE_DENY
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_TRANSACTION):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA:
        return sqlite3.SQLITE_OK if first == 'table_info' and second in REQUIRED else sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION:
        return sqlite3.SQLITE_OK if second in ('length', 'typeof', 'substr', 'glob', 'count', 'sum', 'max') else sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_DENY


@contextmanager
def open_snapshot(path, limits, check):
    check()
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True,
                                timeout=limits['busy_timeout_ms'] / 1000)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        connection.execute('PRAGMA trusted_schema=OFF')
        if hasattr(connection, 'enable_load_extension'):
            connection.enable_load_extension(False)
        connection.set_authorizer(_authorize)
        def interrupt():
            try:
                check()
                return 0
            except SourceUnavailable:
                return 1
        connection.set_progress_handler(interrupt, 1000)
        check()
        connection.execute('BEGIN')
        yield connection
    finally:
        connection.set_progress_handler(None, 0)
        connection.close()


def probe_schema(connection, check):
    check()
    tables = {row['name']: row['type'] for row in connection.execute(
        "SELECT name,type FROM sqlite_master WHERE name IN ('session','message','part')")}
    if any(tables.get(name) != 'table' for name in REQUIRED):
        raise SourceUnavailable('unsupported_source_format', 'OpenCode projection is unsupported')
    for name, required in REQUIRED.items():
        check()
        rows = connection.execute('PRAGMA table_info(' + name + ')').fetchmany(129)
        if len(rows) > 128:
            raise SourceUnavailable('bounded_read', 'OpenCode schema exceeds metadata limits')
        columns = {row['name']: row['type'].upper() for row in rows}
        if any(columns.get(column) != kind for column, kind in required.items()):
            raise SourceUnavailable('unsupported_source_format', 'OpenCode projection columns are unsupported')
    return digest(REQUIRED)


def session_metadata(connection, identity, *, validate=True):
    row = connection.execute(
        'SELECT id,time_created, CASE WHEN length(CAST(project_id AS BLOB))<=200 THEN project_id END AS project_id, '
        'CASE WHEN length(CAST(directory AS BLOB))<=4096 THEN directory END AS directory '
        'FROM session WHERE id=?', (identity,)).fetchone()
    if row is None:
        raise SourceUnavailable('source_changed', 'OpenCode session is missing')
    session = {'id': row['id'], 'projectID': row['project_id'], 'directory': row['directory'],
               'row_time': row['time_created']}
    if not validate:
        return session
    _native_id(session['id'])
    _native_id(session['projectID'])
    if session['directory']:
        session['directory'] = _absolute(session['directory'])
    elif session['directory'] is None:
        raise ValueError('OpenCode directory metadata is unavailable')
    return session


def session_proof(session):
    directory = session['directory']
    if directory:
        try:
            directory = _absolute(directory)
        except ValueError:
            pass
    return digest([session['id'], session['projectID'], directory, session['row_time']])


def _object(raw):
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('OpenCode record must be an object')
    return value


def read_record(connection, session, identity, origin, limits, check, diagnostics):
    """Native columns own linkage; no incomplete text is returned as full evidence."""
    check()
    row = connection.execute(
        'SELECT id,session_id,time_created,length(CAST(data AS BLOB)) AS size, '
        'CASE WHEN length(CAST(data AS BLOB))<=? THEN data END AS data '
        'FROM message WHERE id=? AND session_id=?',
        (limits['info_bytes'], identity, session['id'])).fetchone()
    if row is None:
        raise SourceUnavailable('source_changed', 'OpenCode message is missing')
    base = [session_proof(session), identity, row['time_created'], row['size']]
    if row['data'] is None:
        _diagnostic(diagnostics, 'oversize_record')
        return None, digest([base, 'info_oversize']), row['time_created']
    try:
        info = _object(row['data'])
        if (('id' in info and info['id'] != identity)
                or ('sessionID' in info and info['sessionID'] != session['id'])):
            raise ValueError('Conflicting native message linkage')
        if (not isinstance(info.get('time'), dict) or type(info['time'].get('created')) not in (int, float)
                or info['time']['created'] != row['time_created']):
            raise ValueError('Conflicting native creation timestamps')
        info.update(id=identity, sessionID=session['id'])
    except (ValueError, TypeError, UnicodeError):
        _diagnostic(diagnostics, 'invalid_record')
        return None, digest([base, 'invalid_info', redact(str(row['data']))]), row['time_created']
    foreign = connection.execute('SELECT count(*) FROM part WHERE message_id=? AND session_id<>?',
                                 (identity, session['id'])).fetchone()[0]
    count = connection.execute('SELECT count(*) FROM part WHERE message_id=? AND session_id=?',
                               (identity, session['id'])).fetchone()[0]
    if foreign or count > limits['parts']:
        _diagnostic(diagnostics, 'invalid_record' if foreign else 'oversize_record')
        return None, digest([base, 'part_link_or_count', foreign, count]), row['time_created']
    rows = connection.execute(
        'SELECT id,message_id,session_id,length(CAST(data AS BLOB)) AS size, '
        'CASE WHEN length(CAST(data AS BLOB))<=? THEN data END AS data '
        'FROM part WHERE message_id=? AND session_id=? ORDER BY id LIMIT ?',
        (limits['part_bytes'], identity, session['id'], limits['parts'] + 1))
    parts, sizes, total = [], [], 0
    for part in rows:
        check()
        sizes.append([part['id'], part['size']])
        if part['data'] is None:
            _diagnostic(diagnostics, 'oversize_record')
            return None, digest([base, 'part_oversize', sizes]), row['time_created']
        try:
            value = _object(part['data'])
            _native_id(part['id'])
            if any(key in value and value[key] != expected for key, expected in (
                    ('id', part['id']), ('messageID', identity), ('sessionID', session['id']))):
                raise ValueError('Conflicting native part linkage')
            value.update(id=part['id'], messageID=identity, sessionID=session['id'])
            # Nontext bodies never enter normalization or checkpoint payloads.
            if value.get('type') != 'text':
                value = {key: value[key] for key in ('id', 'messageID', 'sessionID', 'type') if key in value}
            elif isinstance(value.get('text'), str):
                total += len(value['text'].encode('utf-8')) + 1
                if total > limits['message_bytes']:
                    _diagnostic(diagnostics, 'oversize_record')
                    return None, digest([base, 'text_oversize', sizes]), row['time_created']
            parts.append(value)
        except (ValueError, TypeError, UnicodeError):
            _diagnostic(diagnostics, 'invalid_record')
            return None, digest([base, 'invalid_part', sizes]), row['time_created']
    message = normalize_record(session, {'info': info, 'parts': parts}, origin, diagnostics=diagnostics)
    if message is not None:
        proof = digest([message['id'], message['source_locator']['part_ids']])
    else:
        relevant = [{key: value[key] for key in ('id', 'type', 'ignored', 'synthetic', 'text') if key in value}
                    for value in parts if value.get('type') == 'text']
        proof = digest([base, info.get('role'), info.get('time'), info.get('summary'),
                        redact(json.dumps(relevant, sort_keys=True))])
    return message, proof, row['time_created']
