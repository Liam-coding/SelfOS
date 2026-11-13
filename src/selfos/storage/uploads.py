"""Contained immutable upload admission and its dedicated recovery journal."""
import hashlib
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path

from selfos.storage.files import _atomic_write, _locked
from selfos.paths import canonical_path

MAX_BYTES = 20 * 1024 * 1024
MAX_STORAGE = 512 * 1024 * 1024
MAX_DOCUMENTS = 2000
PROFILE = 'plain-text-v1'
EXPORT_PROFILE = 'opencode-export-v1-810c0eb'
_THREAD_LOCK = threading.RLock()


def validate_filename(filename):
    if (not isinstance(filename, str) or not filename or len(filename.encode('utf-8')) > 512
            or any(ord(char) < 32 or ord(char) == 127 or char in '/:' + chr(92) for char in filename)
            or Path(filename).suffix.casefold() not in ('.txt', '.md', '.json')):
        raise ValueError('Unsupported or invalid upload filename')
    return filename


def upload_root(vault):
    vault = canonical_path(vault)
    root = vault / '.knowledge_uploads'
    if root.is_symlink() or (hasattr(root, 'is_junction') and root.is_junction()) or not canonical_path(root).is_relative_to(vault):
        raise ValueError('Upload folder escapes vault')
    root.mkdir(parents=True, exist_ok=True)
    return root


def upload_path(root, name):
    root = canonical_path(root)
    path = root / name
    if not canonical_path(path).is_relative_to(root):
        raise ValueError('Upload path escapes its folder')
    for item in (path, *path.parents):
        if item == root:
            break
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise ValueError('Upload links are not permitted')
    return path


def _hash(path):
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Stored original exceeds size limit')
    return hashlib.sha256(raw).hexdigest()


def _id(content_hash, profile=PROFILE):
    return hashlib.sha256((profile + ':' + content_hash).encode()).hexdigest()


def _entry(value):
    if not isinstance(value, dict):
        raise ValueError('Invalid upload registry')
    content_hash = value.get('content_sha256', '')
    identity = value.get('id', '')
    profile = value.get('profile')
    if (not isinstance(content_hash, str) or not re.fullmatch('[a-f0-9]{64}', content_hash)
            or profile not in (PROFILE, EXPORT_PROFILE) or identity != _id(content_hash, profile)
            or value.get('path') != '.knowledge_uploads/originals/' + identity + '.txt'
            or value.get('provenance') != 'quoted_dialogue'
            or isinstance(value.get('size'), bool) or not isinstance(value.get('size'), int)
            or not 0 < value['size'] <= MAX_BYTES):
        raise ValueError('Invalid upload registry identity')
    validate_filename(value.get('original_filename'))
    aliases = value.get('filenames')
    if not isinstance(aliases, list) or not 1 <= len(aliases) <= 8:
        raise ValueError('Invalid upload filename aliases')
    for name in aliases:
        validate_filename(name)
    if any((Path(name).suffix.casefold() == '.json') != (profile == EXPORT_PROFILE)
           for name in [value['original_filename'], *aliases]):
        raise ValueError('Upload filename does not match explicit adapter profile')
    try:
        stamp = datetime.fromisoformat(value['uploaded_at'])
        if stamp.tzinfo is None:
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise ValueError('Invalid upload timestamp') from None
    return value


def _read(root, path):
    with path.open('rb') as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError('Upload metadata exceeds size limit')
    return json.loads(raw)


def _write(path, value):
    _atomic_write(path, json.dumps(value, ensure_ascii=False).encode('utf-8'))
    with path.open('r+b') as stream:
        os.fsync(stream.fileno())


def _publish_entry(root, document):
    _write(upload_path(root, 'registry/' + document['id'] + '.json'), _entry(document))


def _recover(root):
    journal = upload_path(root, 'admission.json')
    if not journal.exists():
        return
    intent = _read(root, journal)
    if not isinstance(intent, dict) or intent.get('version') != 1:
        raise ValueError('Invalid upload recovery journal')
    document = _entry(intent.get('document'))
    temp_name = intent.get('temporary', '')
    if not isinstance(temp_name, str) or not re.fullmatch(r'incoming/[a-f0-9]{32}[.]tmp', temp_name):
        raise ValueError('Invalid upload temporary identity')
    temp = upload_path(root, temp_name)
    original = upload_path(root, 'originals/' + document['id'] + '.txt')
    expected = document['content_sha256']
    quarantine_name = intent.get('quarantine')
    if quarantine_name is not None:
        if not isinstance(quarantine_name, str) or not re.fullmatch(r'quarantine/[a-f0-9]{32}[.]txt', quarantine_name):
            raise ValueError('Invalid quarantine identity')
        previous_hash = intent.get('previous_sha256', '')
        if not isinstance(previous_hash, str) or not re.fullmatch('[a-f0-9]{64}', previous_hash):
            raise ValueError('Invalid repair identity')
        quarantine = upload_path(root, quarantine_name)
        if quarantine.exists() and _hash(quarantine) != previous_hash:
            raise ValueError('Quarantine content changed')
        if original.exists() and _hash(original) != expected:
            if _hash(original) != previous_hash:
                raise ValueError('Original changed during repair')
            quarantine.parent.mkdir(parents=True, exist_ok=True)
            if quarantine.exists():
                if not os.path.samefile(original, quarantine):
                    raise ValueError('Repair quarantine identity changed')
            else:
                os.link(original, quarantine)
            original.unlink()
    if not original.exists():
        if not temp.is_file() or _hash(temp) != expected:
            raise ValueError('Upload recovery needs its verified original')
        original.parent.mkdir(parents=True, exist_ok=True)
        os.link(temp, original)
    if _hash(original) != expected:
        raise ValueError('Original collision; content will not be replaced')
    _publish_entry(root, document)
    temp.unlink(missing_ok=True)
    journal.unlink()


def _registry(root):
    folder = upload_path(root, 'registry')
    if not folder.exists():
        return []
    result = []
    for path in folder.iterdir():
        if len(result) >= MAX_DOCUMENTS or not re.fullmatch(r'[a-f0-9]{64}[.]json', path.name):
            raise ValueError('Upload registry exceeds limits or is malformed')
        path = upload_path(root, 'registry/' + path.name)
        row = _entry(_read(root, path))
        if path.stem != row['id']:
            raise ValueError('Upload registry identity mismatch')
        result.append(row)
    return result


def _stored_bytes(root):
    total = 0
    count = 0
    for folder_name in ('originals', 'quarantine'):
        folder = upload_path(root, folder_name)
        if not folder.exists():
            continue
        for item in folder.iterdir():
            count += 1
            if count > MAX_DOCUMENTS * 3:
                raise ValueError('Upload storage inventory exceeds limits')
            path = upload_path(root, folder_name + '/' + item.name)
            if not path.is_file():
                raise ValueError('Unexpected upload storage entry')
            total += path.stat().st_size
    return total


def register_document(vault, temporary, filename, content_hash, size, *, profile=PROFILE):
    if profile not in (PROFILE, EXPORT_PROFILE):
        raise ValueError('Unsupported upload adapter profile')
    root = upload_root(vault)
    temporary = Path(temporary)
    with _THREAD_LOCK, _locked(root):
        _recover(root)
        rows = _registry(root)
        identity = _id(content_hash, profile)
        known = next((row for row in rows if row['id'] == identity), None)
        original = upload_path(root, 'originals/' + identity + '.txt')
        additional = 0 if known and original.is_file() and _hash(original) == content_hash else size
        if (known is None and len(rows) >= MAX_DOCUMENTS) or _stored_bytes(root) + additional > MAX_STORAGE:
            raise ValueError('Upload storage limit reached')
        if original.exists() and known is None:
            raise ValueError('Unregistered original collision')
        document = dict(known) if known else dict(id=identity, profile=profile,
            content_sha256=content_hash, size=size, original_filename=filename,
            filenames=[filename], uploaded_at=datetime.now(timezone.utc).isoformat(),
            path='.knowledge_uploads/originals/' + identity + '.txt', provenance='quoted_dialogue')
        if filename not in document['filenames'] and len(document['filenames']) < 8:
            document['filenames'] = [*document['filenames'], filename]
        relative = temporary.relative_to(root).as_posix()
        intent = dict(version=1, temporary=relative, document=document)
        if original.exists() and _hash(original) != content_hash:
            intent.update(quarantine='quarantine/' + uuid.uuid4().hex + '.txt', previous_sha256=_hash(original))
        _write(upload_path(root, 'admission.json'), intent)
        _recover(root)
        return {'document': document, 'duplicate': known is not None}


def recover_uploads(vault):
    root = upload_root(vault)
    with _THREAD_LOCK, _locked(root):
        _recover(root)


@contextmanager
def upload_lock(vault):
    """Serialize external publication with admission's thread/filesystem locks."""
    with _THREAD_LOCK, _locked(upload_root(vault)):
        yield


def discard_transfer(vault, temporary):
    """Remove this transfer only; a durable intent owns its staged bytes."""
    root = upload_root(vault)
    relative = Path(temporary).relative_to(root).as_posix()
    with _THREAD_LOCK, _locked(root):
        journal = upload_path(root, 'admission.json')
        if journal.exists():
            try:
                intent = _read(root, journal)
            except (ValueError, OSError):
                return
            if not isinstance(intent, dict) or intent.get('temporary') == relative:
                return
        upload_path(root, relative).unlink(missing_ok=True)


def list_documents(vault, offset=0, limit=50):
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError('Invalid upload offset')
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError('Invalid upload page size')
    root = upload_root(vault)
    with _THREAD_LOCK, _locked(root):
        _recover(root)
        rows = sorted(_registry(root), key=lambda row: (row['uploaded_at'], row['id']), reverse=True)
        return {'items': rows[offset:offset + limit], 'total': len(rows), 'offset': offset, 'limit': limit}


def get_document(vault, identity):
    if not isinstance(identity, str) or not re.fullmatch('[a-f0-9]{64}', identity):
        raise ValueError('Invalid document identity')
    root = upload_root(vault)
    with _THREAD_LOCK, _locked(root):
        _recover(root)
        path = upload_path(root, 'registry/' + identity + '.json')
        if not path.is_file():
            raise ValueError('Uploaded document is unavailable')
        row = _entry(_read(root, path))
        if row['id'] != identity:
            raise ValueError('Upload registry identity mismatch')
        return row
