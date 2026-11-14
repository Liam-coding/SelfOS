"""Bounded, append-only sealed document parts; independent of model work."""
import hashlib
import json
import re
import threading

from selfos.storage.files import _locked
from selfos.storage.uploads import get_document, upload_path, upload_root, _hash, _write
from selfos.sources.upload_text import normalize_document, document_part, MAX_NORMALIZED_BYTES
from selfos.sources.documents import NORMALIZATION_VERSION
from selfos.knowledge.identity import digest
from selfos.storage.uploads import EXPORT_PROFILE
from selfos.storage.opencode_exports import index_export, export_sessions, export_status

_INDEX_LOCK = threading.RLock()


def _folder(vault, identity, part_chars):
    if type(part_chars) is not int or part_chars not in (16000, 24000):
        raise ValueError('Unsupported document part size')
    profile = digest([NORMALIZATION_VERSION, part_chars])
    return upload_path(upload_root(vault), 'index/' + digest([identity, profile])[:24]), profile


def _read(path, maximum):
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('Document index exceeds local limit')
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError('Invalid document index; retained checkpoint needs repair') from None


def _write_manifest(path, value):
    raw = json.dumps(value, ensure_ascii=False).encode('utf-8')
    if len(raw) > 1024 * 1024:
        raise ValueError('Document manifest exceeds local limit')
    _write(path, value)


def _verify_original(vault, document):
    path = upload_path(upload_root(vault), 'originals/' + document['id'] + '.txt')
    if not path.is_file() or _hash(path) != document['content_sha256']:
        raise ValueError('Uploaded original is missing or changed')


def _load(folder, document, profile, part_chars):
    manifest = _read(upload_path(folder, 'manifest.json'), 1024 * 1024)
    if (not isinstance(manifest, dict) or manifest.get('version') != 1
            or manifest.get('document_id') != document['id'] or manifest.get('profile') != profile
            or manifest.get('content_sha256') != document['content_sha256']
            or manifest.get('normalization_version') != NORMALIZATION_VERSION
            or manifest.get('part_chars') != part_chars or type(manifest.get('cursor')) is not int
            or type(manifest.get('text_length')) is not int or not 0 <= manifest['text_length'] <= MAX_NORMALIZED_BYTES
            or manifest.get('total_slots') != (manifest['text_length'] + part_chars - 1) // part_chars
            or not 0 <= manifest['cursor'] <= manifest['total_slots']
            or not isinstance(manifest.get('slots'), list) or len(manifest['slots']) != manifest['cursor']):
        raise ValueError('Invalid document index checkpoint')
    if (any(not isinstance(row, dict) or set(row) != {'id', 'eligible'}
            or not isinstance(row['id'], str) or not re.fullmatch('[a-f0-9]{64}', row['id'])
            or type(row['eligible']) is not bool for row in manifest['slots'])
            or len({row['id'] for row in manifest['slots']}) != len(manifest['slots'])):
        raise ValueError('Invalid document index checkpoint')
    with upload_path(folder, 'normalized.txt').open('rb') as stream:
        raw = stream.read(MAX_NORMALIZED_BYTES + 1)
    if len(raw) > MAX_NORMALIZED_BYTES or hashlib.sha256(raw).hexdigest() != manifest.get('text_sha256'):
        raise ValueError('Normalized document index changed')
    text = raw.decode('utf-8')
    if len(text) != manifest['text_length']:
        raise ValueError('Normalized document coordinates changed')
    return manifest, text


def _result(manifest, stopped=False):
    ids = [row['id'] for row in manifest['slots'] if row['eligible']]
    status = ('stopped' if stopped else 'indexing' if manifest['cursor'] < manifest['total_slots']
              else 'ready' if ids else 'no_eligible_knowledge')
    return dict(document_id=manifest['document_id'], profile=manifest['profile'],
                status=status, cursor=manifest['cursor'], total_slots=manifest['total_slots'], part_ids=ids)


def index_document(vault, document_id, *, cancel=lambda: False, max_parts=2, part_chars=24000):
    if type(max_parts) is not int or not 1 <= max_parts <= 10:
        raise ValueError('Invalid document indexing allowance')
    document = get_document(vault, document_id)
    if document['profile'] == EXPORT_PROFILE:
        return index_export(vault, document_id, cancel=cancel, max_parts=max_parts, part_chars=part_chars)
    _verify_original(vault, document)
    folder, profile = _folder(vault, document_id, part_chars)
    with _INDEX_LOCK, _locked(folder):
        path = upload_path(folder, 'manifest.json')
        if path.exists():
            manifest, text = _load(folder, document, profile, part_chars)
        else:
            if cancel():
                return dict(document_id=document_id, profile=profile, status='stopped', cursor=0,
                            total_slots=None, part_ids=[])
            text = normalize_document(vault, document)
            raw = text.encode('utf-8')
            # Normalized bytes are disposable; cursor publication is authoritative.
            from selfos.storage.files import _atomic_write
            _atomic_write(upload_path(folder, 'normalized.txt'), raw)
            manifest = dict(version=1, document_id=document_id, profile=profile,
                content_sha256=document['content_sha256'], normalization_version=NORMALIZATION_VERSION,
                text_sha256=hashlib.sha256(raw).hexdigest(), text_length=len(text), part_chars=part_chars,
                total_slots=(len(text) + part_chars - 1) // part_chars, cursor=0, slots=[])
            _write_manifest(path, manifest)
        for _ in range(max_parts):
            if cancel() or manifest['cursor'] == manifest['total_slots']:
                break
            number = manifest['cursor']
            session = document_part(document, text, manifest['text_sha256'], profile, number, part_chars)
            part_id = digest([document_id, profile, number, session['fingerprint']])
            part_path = upload_path(folder, 'parts/' + part_id[:24] + '.json')
            if part_path.exists() and _read(part_path, 1024 * 1024) != session:
                raise ValueError('Document part storage identity collision')
            _write(part_path, session)
            # A failed cursor write leaves a deterministic, replaceable orphan part.
            candidate = {**manifest, 'cursor': number + 1,
                'slots': [*manifest['slots'], dict(id=part_id, eligible=bool(session['messages']))]}
            _verify_original(vault, document)
            _write_manifest(path, candidate)
            manifest = candidate
        return _result(manifest, stopped=cancel())


def document_sessions(vault, document_id, part_ids, *, part_chars=24000):
    if (not isinstance(part_ids, list) or len(part_ids) > 4096 or len(set(part_ids)) != len(part_ids)
            or any(not isinstance(item, str) or not re.fullmatch('[a-f0-9]{64}', item) for item in part_ids)):
        raise ValueError('Invalid selected document parts')
    document = get_document(vault, document_id)
    if document['profile'] == EXPORT_PROFILE:
        return export_sessions(vault, document_id, part_ids, part_chars=part_chars)
    _verify_original(vault, document)
    folder, profile = _folder(vault, document_id, part_chars)
    with _INDEX_LOCK, _locked(folder):
        manifest, text = _load(folder, document, profile, part_chars)
        eligible = {row['id']: number for number, row in enumerate(manifest['slots']) if row['eligible']}
        if any(identity not in eligible for identity in part_ids):
            raise ValueError('Selected part does not belong to document')
        result = []
        for identity in part_ids:
            session = _read(upload_path(folder, 'parts/' + identity[:24] + '.json'), 1024 * 1024)
            expected = document_part(document, text, manifest['text_sha256'], profile, eligible[identity], part_chars)
            if session != expected or digest([document_id, profile, eligible[identity], expected['fingerprint']]) != identity:
                raise ValueError('Document part changed')
            result.append(session)
        return result


def document_messages(vault, document_id, part_ids, *, part_chars=24000):
    return [message for session in document_sessions(vault, document_id, part_ids, part_chars=part_chars)
            for message in session['messages']]


def index_status(vault, document_id, *, part_chars=24000):
    document = get_document(vault, document_id)
    if document['profile'] == EXPORT_PROFILE:
        return export_status(vault, document_id, part_chars=part_chars)
    _verify_original(vault, document)
    folder, profile = _folder(vault, document_id, part_chars)
    if not upload_path(folder, 'manifest.json').exists():
        return dict(document_id=document_id, profile=profile, status='uploaded', cursor=0,
                    total_slots=None, part_ids=[])
    with _INDEX_LOCK, _locked(folder):
        manifest, _ = _load(folder, document, profile, part_chars)
        return _result(manifest)
