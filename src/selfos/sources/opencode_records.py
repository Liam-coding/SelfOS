"""Pinned OpenCode wire normalization; adapters own IO and source permissions."""
import copy
import hashlib
import math
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath

from selfos.paths import canonical_path
from selfos.sources.compaction import canonical_project
from selfos.sources.text import redact, _is_meaningful
from selfos.knowledge.filtering import content_identity
from selfos.knowledge.identity import digest

PROFILE = 'opencode-v1-810c0eb'
NAMESPACE = 'selfos-opencode-message-v1'
MAX_MESSAGE_BYTES = 256 * 1024
MAX_PARTS = 256
MAX_LOCATORS = 8
METADATA_FIELDS = ('id', 'path', 'timestamp', 'role', 'source', 'project_id', 'session_id', 'provenance',
    'cwd', 'native_project_id', 'native_session_id', 'native_message_id', 'source_locator',
    'source_locators', 'document_id', 'content_sha256', 'original_filename')
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,199}')
_HASH = re.compile(r'[a-f0-9]{64}')


def _diagnostic(target, code, **metadata):
    if target is not None and len(target) < 100:
        target.append({'code': code, **metadata})


def _native_id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError('Invalid native OpenCode identity')
    return value


def _absolute(value):
    if (not isinstance(value, str) or not value or len(value) > 4096
            or any(ord(char) < 32 for char in value) or not Path(value).is_absolute()):
        raise ValueError('OpenCode paths must be explicit absolute paths')
    return str(canonical_path(value)).replace(chr(92), '/')


def _directory(value):
    """Directory is descriptive metadata; foreign paths must never become local IO targets."""
    if (not isinstance(value, str) or not value or len(value) > 4096 or any(ord(char) < 32 for char in value)):
        raise ValueError('Invalid OpenCode directory metadata')
    if Path(value).is_absolute():
        return _absolute(value)
    for path_type in (PureWindowsPath, PurePosixPath):
        path = path_type(value)
        if path.is_absolute() and '..' not in path.parts:
            return path.as_posix()
    raise ValueError('OpenCode directory must be an absolute path')


def _origin(value, path_validator=_absolute):
    """Only adapter-owned origin metadata; document adapters verify admission first."""
    if not isinstance(value, dict) or value.get('kind') not in ('database', 'document'):
        raise ValueError('Invalid OpenCode source origin')
    keys = {'kind', 'path'}
    if value['kind'] == 'document':
        keys |= {'document_id', 'content_sha256', 'original_filename'}
    if set(value) != keys:
        raise ValueError('Invalid OpenCode origin fields')
    result = {**value, 'path': path_validator(value['path'])}
    if value['kind'] == 'document':
        for key in ('document_id', 'content_sha256'):
            if not isinstance(value[key], str) or not _HASH.fullmatch(value[key]):
                raise ValueError('Invalid admitted document identity')
        filename = value['original_filename']
        if not isinstance(filename, str) or not filename or len(filename) > 255 or any(ord(c) < 32 for c in filename):
            raise ValueError('Invalid admitted document filename')
    return result


def _timestamp(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('Invalid OpenCode creation time')
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _logical_identity(message):
    return digest([NAMESPACE, message['native_project_id'], message['native_session_id'],
        message['native_message_id'], message['cwd'], message['timestamp'], message['role'],
        message['provenance'], hashlib.sha256(message['text'].encode('utf-8')).hexdigest()])


def normalize_record(session, record, origin, *, diagnostics=None):
    """Normalize the pinned WithParts record, never synthesizing native linkage."""
    try:
        if not isinstance(session, dict) or not isinstance(record, dict):
            raise ValueError('Invalid OpenCode wire record')
        info, parts = record.get('info'), record.get('parts')
        if not isinstance(info, dict) or not isinstance(parts, list) or len(parts) > MAX_PARTS:
            raise ValueError('Invalid OpenCode message parts')
        project = _native_id(session.get('projectID'))
        session_id, message_id = _native_id(session.get('id')), _native_id(info.get('id'))
        if info.get('sessionID') != session_id or info.get('role') not in ('user', 'assistant'):
            raise ValueError('Invalid OpenCode message linkage or role')
        if not isinstance(info.get('time'), dict):
            raise ValueError('Missing OpenCode creation time')
        timestamp = _timestamp(info['time'].get('created'))
        directory = session.get('directory')
        directory = '' if directory is None or directory == '' else _directory(directory)
        owned_origin = _origin(origin)
        if info['role'] == 'assistant' and info.get('summary') is True:
            _diagnostic(diagnostics, 'filtered_message')
            return None
        identities, included, size = set(), [], 0
        for part in parts:
            if not isinstance(part, dict):
                raise ValueError('Invalid OpenCode part')
            part_id = _native_id(part.get('id'))
            if (part_id in identities or part.get('sessionID') != session_id
                    or part.get('messageID') != message_id or not isinstance(part.get('type'), str)):
                raise ValueError('Invalid or duplicate OpenCode part linkage')
            identities.add(part_id)
            if any(flag in part and type(part[flag]) is not bool for flag in ('ignored', 'synthetic')):
                raise ValueError('Invalid OpenCode part flags')
            if part['type'] != 'text' or part.get('ignored') is True or part.get('synthetic') is True:
                _diagnostic(diagnostics, 'filtered_part')
                continue
            text = part.get('text')
            if not isinstance(text, str):
                raise ValueError('Invalid OpenCode text part')
            size += len(text.encode('utf-8')) + 1
            if size > MAX_MESSAGE_BYTES:
                raise ValueError('OpenCode message exceeds normalization limit')
            included.append((part_id, text))
        included.sort()
        text = redact('\n'.join(value for _, value in included)).strip()
        if len(text.encode('utf-8')) > MAX_MESSAGE_BYTES:
            raise ValueError('Normalized OpenCode message exceeds limit')
        if (not text or (info['role'] == 'user' and not _is_meaningful(text))
                or any(marker in text for marker in ('<environment_context>', '<INSTRUCTIONS>',
                    '<system-reminder>', '<task-notification>'))):
            _diagnostic(diagnostics, 'filtered_message')
            return None
        provenance = content_identity({'role': info['role'], 'text': text})
        if provenance in ('runtime_output', 'machine_summary', 'agent_status', 'runtime_evidence'):
            _diagnostic(diagnostics, 'filtered_message')
            return None
        if owned_origin['kind'] == 'document':
            provenance = 'quoted_dialogue'
        locator = {**owned_origin, 'version': 1, 'profile': PROFILE, 'project_id': project,
            'session_id': session_id, 'message_id': message_id,
            'part_ids': [identity for identity, _ in included],
            'text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}
        normalized = dict(source='opencode', role=info['role'], timestamp=timestamp, text=text,
            project=redact(Path(directory).name) if directory else 'OpenCode project',
            project_id=canonical_project(directory) if directory else 'opencode-project:' + project,
            cwd=directory, session_id=('opencode-export:' + session_id if owned_origin['kind'] == 'document' else session_id),
            path=owned_origin['path'], provenance=provenance,
            native_project_id=project, native_session_id=session_id, native_message_id=message_id,
            native_created_ms=info['time']['created'], source_locator=locator, source_locators=[copy.deepcopy(locator)])
        if owned_origin['kind'] == 'document':
            normalized.update({key: owned_origin[key] for key in ('document_id', 'content_sha256', 'original_filename')})
        normalized['id'] = _logical_identity(normalized)
        locator['source_id'] = normalized['id']
        normalized['source_locators'] = [copy.deepcopy(locator)]
        return normalized
    except (ValueError, TypeError, OverflowError, OSError):
        _diagnostic(diagnostics, 'invalid_record')
        return None


def _check_locator(locator, message):
    if not isinstance(locator, dict) or locator.get('version') != 1 or locator.get('profile') != PROFILE:
        raise ValueError('Invalid OpenCode locator profile')
    origin_keys = {'kind', 'path'}
    if locator.get('kind') == 'document':
        origin_keys |= {'document_id', 'content_sha256', 'original_filename'}
    metadata_keys = {'version', 'profile', 'project_id', 'session_id', 'message_id', 'part_ids', 'text_sha256', 'source_id'}
    if set(locator) != origin_keys | metadata_keys:
        raise ValueError('Invalid OpenCode locator fields')
    _origin({key: locator[key] for key in origin_keys})
    if (locator['source_id'] != message['id'] or locator['project_id'] != message['native_project_id']
            or locator['session_id'] != message['native_session_id']
            or locator['message_id'] != message['native_message_id']
            or locator['text_sha256'] != hashlib.sha256(message['text'].encode('utf-8')).hexdigest()
            or not isinstance(locator['part_ids'], list) or not 1 <= len(locator['part_ids']) <= MAX_PARTS):
        raise ValueError('OpenCode locator semantic metadata changed')
    if len({_native_id(identity) for identity in locator['part_ids']}) != len(locator['part_ids']):
        raise ValueError('Duplicate OpenCode locator parts')


def opencode_metadata(message, existing=None, *, path_validator=_absolute):
    """Retain adapter-owned metadata; fresh byte verification remains an IO boundary."""
    if message.get('source') != 'opencode' or not isinstance(message.get('id'), str) or not _HASH.fullmatch(message['id']):
        raise ValueError('Invalid OpenCode source metadata')
    for key in ('native_project_id', 'native_session_id', 'native_message_id'):
        _native_id(message.get(key))
    timestamp = message.get('timestamp')
    try:
        instant = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        if instant.tzinfo is None or instant.utcoffset().total_seconds() != 0:
            raise ValueError('Invalid OpenCode timestamp')
    except (AttributeError, TypeError, ValueError):
        raise ValueError('Invalid OpenCode timestamp') from None
    if (message.get('role') not in ('user', 'assistant') or
            message.get('provenance') not in ('user_statement', 'assistant_suggestion', 'quoted_dialogue') or
            not isinstance(message.get('project_id'), str) or not message['project_id'] or
            not isinstance(message.get('cwd'), str)):
        raise ValueError('Invalid OpenCode semantic source fields')
    if message['cwd']:
        _directory(message['cwd'])
    locators = message.get('source_locators')
    if not isinstance(locators, list) or not 1 <= len(locators) <= MAX_LOCATORS:
        raise ValueError('Missing OpenCode copy locators')
    for locator in locators:
        # A compact piece preserves the original logical ID and text digest;
        # it must not recompute that identity from its shorter slice.
        if (not isinstance(locator, dict) or locator.get('source_id') != message['id']
                or locator.get('profile') != PROFILE or locator.get('version') != 1
                or locator.get('project_id') != message.get('native_project_id')
                or locator.get('session_id') != message.get('native_session_id')
                or locator.get('message_id') != message.get('native_message_id')):
            raise ValueError('OpenCode locator metadata conflicts with source')
        origin_keys = ('kind', 'path') if locator.get('kind') == 'database' else (
            'kind', 'path', 'document_id', 'content_sha256', 'original_filename')
        _origin({key: locator.get(key) for key in origin_keys}, path_validator)
        metadata_keys = {'version', 'profile', 'project_id', 'session_id', 'message_id', 'part_ids', 'text_sha256', 'source_id'}
        if (set(locator) != set(origin_keys) | metadata_keys or not isinstance(locator.get('text_sha256'), str)
                or not _HASH.fullmatch(locator['text_sha256']) or not isinstance(locator.get('part_ids'), list)
                or not 1 <= len(locator['part_ids']) <= MAX_PARTS
                or len({_native_id(value) for value in locator['part_ids']}) != len(locator['part_ids'])):
            raise ValueError('Invalid OpenCode locator structure')
        expected_id = digest([NAMESPACE, message['native_project_id'], message['native_session_id'],
            message['native_message_id'], message['cwd'], timestamp, message['role'],
            message['provenance'], locator['text_sha256']])
        expected_session = ('opencode-export:' if locator['kind'] == 'document' else '') + message['native_session_id']
        if message['id'] != expected_id or message.get('session_id') != expected_session:
            raise ValueError('OpenCode semantic metadata does not match its identity')
    if message.get('source_locator') not in locators:
        raise ValueError('OpenCode primary locator is not a registered copy')
    result = {key: copy.deepcopy(message[key]) for key in METADATA_FIELDS if key in message}
    if existing:
        semantic = ('id', 'timestamp', 'role', 'source', 'project_id', 'session_id', 'provenance',
                    'cwd', 'native_project_id', 'native_session_id', 'native_message_id')
        if any(existing.get(key) != result.get(key) for key in semantic):
            raise ValueError('OpenCode source identity changed')
        previous = opencode_metadata(existing, path_validator=path_validator)
        for locator in previous['source_locators']:
            if locator not in result['source_locators'] and len(result['source_locators']) < MAX_LOCATORS:
                result['source_locators'].append(copy.deepcopy(locator))
    return result


def merge_records(messages, *, diagnostics=None):
    """Merge exact semantic copies only; conflicting native keys retain both IDs."""
    merged, native = {}, {}
    for message in messages:
        if not isinstance(message, dict) or message.get('source') != 'opencode':
            raise ValueError('Invalid normalized OpenCode message')
        try:
            if message['id'] != _logical_identity(message):
                raise ValueError('OpenCode logical identity changed')
            locators = message.get('source_locators', [message['source_locator']])
            if not isinstance(locators, list) or not 1 <= len(locators) <= MAX_LOCATORS:
                raise ValueError('Invalid OpenCode locator list')
            for locator in locators:
                _check_locator(locator, message)
            key = (message['native_project_id'], message['native_session_id'], message['native_message_id'])
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError('Invalid normalized OpenCode message') from error
        previous = native.setdefault(key, message['id'])
        if previous != message['id']:
            _diagnostic(diagnostics, 'metadata_conflict', source_id=message['id'])
        if message['id'] not in merged:
            merged[message['id']] = copy.deepcopy(message)
            continue
        target = merged[message['id']]['source_locators']
        for locator in locators:
            if locator in target:
                continue
            if len(target) == MAX_LOCATORS:
                _diagnostic(diagnostics, 'locator_limit', source_id=message['id'])
            else:
                target.append(copy.deepcopy(locator))
    return sorted(merged.values(), key=lambda message: (message['timestamp'], message['id']))
