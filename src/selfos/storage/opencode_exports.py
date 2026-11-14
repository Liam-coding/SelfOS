"""Verified immutable export reads and bounded selected-part indexing."""
import json
import hashlib
import threading

from selfos.storage.uploads import get_document, upload_root, upload_path, _hash, _write
from selfos.storage.files import _locked
from selfos.sources.opencode_export import parse_export, EXPORT_PROFILE, MAX_BYTES
from selfos.sources.compaction import prepare_sessions
from selfos.knowledge.identity import digest

_INDEX_LOCK = threading.RLock()


def read_export(vault, document_id):
    document = get_document(vault, document_id)
    if document['profile'] != EXPORT_PROFILE:
        raise ValueError('Document is not a supported OpenCode export')
    original = upload_path(upload_root(vault), document['path'].split('.knowledge_uploads/', 1)[1])
    if not original.is_file() or _hash(original) != document['content_sha256']:
        raise ValueError('OpenCode export original is missing or changed')
    with original.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) != document['size'] or hashlib.sha256(raw).hexdigest() != document['content_sha256']:
        raise ValueError('OpenCode export changed while reading')
    return parse_export(raw, dict(kind='document', path=str(original), document_id=document['id'],
        content_sha256=document['content_sha256'], original_filename=document['original_filename']))


def resolve_export(vault, locator):
    if not isinstance(locator, dict) or locator.get('kind') != 'document':
        raise ValueError('Invalid OpenCode export locator')
    parsed = read_export(vault, locator.get('document_id'))
    message = next((message for message in parsed['messages'] if message['id'] == locator.get('source_id')), None)
    if message is None or message['source_locator'] != locator:
        raise ValueError('OpenCode export source is missing or changed')
    return message


def _index(vault, document_id, part_chars):
    if type(part_chars) is not int or part_chars not in (16000, 24000):
        raise ValueError('Unsupported export part size')
    profile = digest([EXPORT_PROFILE, part_chars])
    folder = upload_path(upload_root(vault), 'index/' + digest([document_id, profile])[:24])
    return folder, profile


def _part_id(document_id, profile, part):
    return digest([document_id, profile, part['part'], part['fingerprint']])


def _load(vault, document_id, part_chars, folder, profile):
    parsed = read_export(vault, document_id)
    sessions = prepare_sessions(parsed['messages'], max_chars=part_chars)
    ids = [_part_id(document_id, profile, part) for part in sessions]
    path = upload_path(folder, 'manifest.json')
    manifest = dict(version=1, document_id=document_id, profile=profile, part_chars=part_chars,
                    cursor=0, total_slots=len(sessions), part_ids=[])
    if path.exists():
        with path.open('rb') as stream:
            raw = stream.read(1024*1024 + 1)
        if len(raw) > 1024*1024:
            raise ValueError('Export index exceeds allowance')
        manifest = json.loads(raw)
        if (not isinstance(manifest, dict) or set(manifest) != {'version', 'document_id', 'profile',
                'part_chars', 'cursor', 'total_slots', 'part_ids'} or manifest['version'] != 1
                or manifest['document_id'] != document_id or manifest['profile'] != profile
                or manifest['part_chars'] != part_chars or manifest['total_slots'] != len(sessions)
                or type(manifest['cursor']) is not int or not 0 <= manifest['cursor'] <= len(sessions)
                or manifest['part_ids'] != ids[:manifest['cursor']]):
            raise ValueError('Export index changed or is invalid')
    return manifest, sessions, ids


def _result(manifest, stopped=False):
    return {**manifest, 'status': 'stopped' if stopped else 'indexing' if manifest['cursor'] < manifest['total_slots']
            else 'ready' if manifest['part_ids'] else 'no_eligible_knowledge'}


def index_export(vault, document_id, *, cancel=lambda: False, max_parts=2, part_chars=24000):
    if type(max_parts) is not int or not 1 <= max_parts <= 10:
        raise ValueError('Invalid export indexing allowance')
    folder, profile = _index(vault, document_id, part_chars)
    with _INDEX_LOCK, _locked(folder):
        manifest, sessions, ids = _load(vault, document_id, part_chars, folder, profile)
        if not cancel():
            number = min(manifest['cursor'] + max_parts, len(sessions))
            manifest = {**manifest, 'cursor': number, 'part_ids': ids[:number]}
            _write(upload_path(folder, 'manifest.json'), manifest)
        return _result(manifest, stopped=cancel())


def export_sessions(vault, document_id, part_ids, *, part_chars=24000):
    if (not isinstance(part_ids, list) or any(not isinstance(item, str) for item in part_ids)
            or len(set(part_ids)) != len(part_ids) or len(part_ids) > 4096):
        raise ValueError('Invalid selected export parts')
    folder, profile = _index(vault, document_id, part_chars)
    with _INDEX_LOCK, _locked(folder):
        manifest, sessions, ids = _load(vault, document_id, part_chars, folder, profile)
        if set(part_ids) - set(manifest['part_ids']):
            raise ValueError('Selected export part is not indexed or does not belong to document')
        return [dict(sessions[ids.index(identity)], upload_document_id=document_id,
                     upload_part_id=identity, upload_profile=profile) for identity in part_ids]


def export_status(vault, document_id, *, part_chars=24000):
    folder, profile = _index(vault, document_id, part_chars)
    with _INDEX_LOCK, _locked(folder):
        manifest, _, _ = _load(vault, document_id, part_chars, folder, profile)
        return _result(manifest)
