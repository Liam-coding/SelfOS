"""Strict pinned OpenCode export parsing, separate from immutable admission IO."""
import copy
import json

from selfos.sources.opencode_records import normalize_record, _native_id, _timestamp, _origin

EXPORT_PROFILE = 'opencode-export-v1-810c0eb'
MAX_BYTES = 20 * 1024 * 1024
MAX_MESSAGES = 2000
MAX_INFO_BYTES = 64 * 1024
MAX_PART_BYTES = 256 * 1024
MAX_TEXT_BYTES = 8 * 1024 * 1024


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('Duplicate OpenCode export JSON key')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('Nonfinite export JSON number')


def _bounded(value, maximum):
    if len(json.dumps(value, ensure_ascii=False).encode('utf-8')) > maximum:
        raise ValueError('OpenCode export record exceeds size allowance')


def parse_export(raw, origin):
    """Unknown JSON is rejected, never traversed heuristically or treated as a user statement."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError('OpenCode export exceeds byte allowance')
    owned = _origin(origin)
    if owned['kind'] != 'document':
        raise ValueError('Export requires immutable document provenance')
    try:
        value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, RecursionError):
        raise ValueError('OpenCode export must be bounded UTF-8 JSON') from None
    if (not isinstance(value, dict) or set(value) != {'info', 'messages'}
            or not isinstance(value['info'], dict) or not isinstance(value['messages'], list)
            or len(value['messages']) > MAX_MESSAGES):
        raise ValueError('Unsupported OpenCode export shape')
    session = copy.deepcopy(value['info'])
    _bounded(session, MAX_INFO_BYTES)
    _native_id(session.get('id'))
    _native_id(session.get('projectID'))
    if not isinstance(session.get('directory'), str):
        raise ValueError('Missing OpenCode export directory metadata')
    diagnostics, messages, seen, text_bytes = [], [], set(), 0
    sanitized = session['directory'] == '[redacted:session-directory:' + session['id'] + ']'
    if sanitized:
        session['directory'] = ''
        diagnostics.append({'code': 'sanitized_export'})
    for wire in value['messages']:
        if (not isinstance(wire, dict) or set(wire) != {'info', 'parts'}
                or not isinstance(wire['info'], dict) or not isinstance(wire['parts'], list)
                or len(wire['parts']) > 256):
            raise ValueError('Unsupported OpenCode export message')
        info = wire['info']
        _bounded(info, MAX_INFO_BYTES)
        identity = _native_id(info.get('id'))
        if identity in seen or info.get('sessionID') != session['id'] or info.get('role') not in ('user', 'assistant'):
            raise ValueError('Invalid or duplicate OpenCode export message linkage')
        seen.add(identity)
        if not isinstance(info.get('time'), dict):
            raise ValueError('Missing OpenCode export creation time')
        _timestamp(info['time'].get('created'))
        record = copy.deepcopy(wire)
        parts_seen = set()
        for part in record['parts']:
            if not isinstance(part, dict):
                raise ValueError('Invalid OpenCode export part')
            _bounded(part, MAX_PART_BYTES)
            part_id = _native_id(part.get('id'))
            if (part_id in parts_seen or part.get('messageID') != identity
                    or part.get('sessionID') != session['id'] or not isinstance(part.get('type'), str)):
                raise ValueError('Invalid OpenCode export part linkage')
            parts_seen.add(part_id)
            if part['type'] == 'text' and part.get('text') == '[redacted:text:' + part_id + ']':
                part['ignored'] = True
                if not sanitized:
                    sanitized = True
                    diagnostics.append({'code': 'sanitized_export'})
        errors = []
        message = normalize_record(session, record, owned, diagnostics=errors)
        if any(row['code'] in ('invalid_record', 'oversize_record') for row in errors):
            raise ValueError('Invalid OpenCode export evidence')
        if message is not None:
            text_bytes += len(json.dumps(message, ensure_ascii=False).encode('utf-8'))
            if text_bytes > MAX_TEXT_BYTES:
                raise ValueError('OpenCode export normalized payload exceeds allowance')
            messages.append(message)
    return dict(messages=messages, diagnostics=diagnostics, native_session_id=session['id'])
