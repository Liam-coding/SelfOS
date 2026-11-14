import hashlib
import io
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest


def admit(vault, name, raw, **kwargs):
    from selfos.sources.upload_admission import admit_document
    return admit_document(vault, name, io.BytesIO(raw), len(raw), **kwargs)


def entries(vault):
    from selfos.storage.uploads import list_documents
    return list_documents(vault)['items']


def test_preserves_original_bom_bytes_and_untrusted_provenance(tmp_path):
    raw = bytes([239, 187, 191]) + b'# Synthetic project. Use checkpoints.'
    result = admit(tmp_path, 'summary.md', raw)
    doc = result['document']
    assert result['duplicate'] is False
    assert (tmp_path / doc['path']).read_bytes() == raw
    assert doc['content_sha256'] == hashlib.sha256(raw).hexdigest()
    assert doc['original_filename'] == 'summary.md'
    assert doc['provenance'] == 'quoted_dialogue'
    assert entries(tmp_path)[0]['id'] == doc['id']


def test_duplicate_formats_reuse_identity_timestamp_and_original(tmp_path):
    raw = b'Synthetic AI description of an import project.'
    first = admit(tmp_path, 'first.txt', raw)['document']
    second = admit(tmp_path, 'second.md', raw)
    assert second['duplicate'] is True
    assert second['document']['id'] == first['id']
    assert second['document']['uploaded_at'] == first['uploaded_at']
    assert second['document']['path'] == first['path']
    assert len(entries(tmp_path)) == 1
    assert len(list((tmp_path / '.knowledge_uploads/originals').iterdir())) == 1


@pytest.mark.parametrize('name', ['../x.txt', 'a/b.md', 'a' + chr(92) + 'b.txt', 'C:x.txt',
                                  'x.txt' + chr(0), 'line' + chr(10) + '.md', 'image.png', 'data.json', 'x' * 513 + '.txt'])
def test_invalid_filename_never_creates_ready_original(tmp_path, name):
    with pytest.raises(ValueError):
        admit(tmp_path, name, b'Synthetic document.')
    assert not list(tmp_path.rglob('*.txt'))


@pytest.mark.parametrize('raw', [b'', bytes([255, 254]) + b'invalid', b'hello' + bytes([0]) + b'binary'])
def test_invalid_content_is_not_admitted(tmp_path, raw):
    with pytest.raises(ValueError):
        admit(tmp_path, 'summary.txt', raw)
    assert entries(tmp_path) == []


@pytest.mark.parametrize('length', [0, -1, True, 20 * 1024 * 1024 + 1])
def test_invalid_length_rejected_before_body_read(tmp_path, length):
    from selfos.sources.upload_admission import admit_document
    class Unreadable:
        def read(self, size):
            pytest.fail('Invalid length must be rejected before reading')
    with pytest.raises(ValueError):
        admit_document(tmp_path, 'summary.txt', Unreadable(), length)


def test_premature_eof_and_cancel_leave_no_ready_entry(tmp_path):
    from selfos.sources.upload_admission import admit_document
    with pytest.raises(ValueError):
        admit_document(tmp_path, 'summary.txt', io.BytesIO(b'Short'), 100)
    with pytest.raises(ValueError):
        admit(tmp_path, 'summary.txt', b'Synthetic document.', cancel=lambda: True)
    assert entries(tmp_path) == []
    assert not list((tmp_path / '.knowledge_uploads/incoming').glob('*'))


def test_concurrent_duplicate_admissions_publish_one_document(tmp_path):
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda n: admit(tmp_path, f'copy{n}.txt', b'Synthetic duplicate.'), range(3)))
    assert len({r['document']['id'] for r in results}) == 1
    assert sum(not r['duplicate'] for r in results) == 1
    assert len(entries(tmp_path)) == 1


def test_changed_original_repair_keeps_modified_bytes_in_quarantine(tmp_path):
    raw = b'Synthetic source before an external edit.'
    first = admit(tmp_path, 'summary.txt', raw)['document']
    original = tmp_path / first['path']
    original.write_bytes(b'Externally modified source, preserve this.')
    repaired = admit(tmp_path, 'summary.txt', raw)
    assert repaired['document']['id'] == first['id']
    assert original.read_bytes() == raw
    quarantined = [p for p in (tmp_path / '.knowledge_uploads/quarantine').iterdir() if p.is_file()]
    assert any(p.read_bytes() == b'Externally modified source, preserve this.' for p in quarantined)


def test_missing_original_reupload_repairs_same_identity(tmp_path):
    raw = b'Synthetic recoverable original.'
    first = admit(tmp_path, 'summary.txt', raw)['document']
    (tmp_path / first['path']).unlink()
    repaired = admit(tmp_path, 'again.md', raw)
    assert repaired['document']['id'] == first['id']
    assert (tmp_path / first['path']).read_bytes() == raw


def test_corrupt_registry_does_not_reset_to_empty(tmp_path):
    doc = admit(tmp_path, 'summary.txt', b'Synthetic record.')['document']
    path = tmp_path / '.knowledge_uploads/registry' / (doc['id'] + '.json')
    path.write_bytes(b'not JSON')
    with pytest.raises(ValueError):
        entries(tmp_path)
    assert path.read_bytes() == b'not JSON'


def test_registry_failure_after_original_install_is_recoverable(tmp_path, monkeypatch):
    from selfos.storage import uploads
    real = uploads._publish_entry
    def fail(*args):
        raise OSError('Synthetic registry publication failure')
    monkeypatch.setattr(uploads, '_publish_entry', fail)
    with pytest.raises(OSError):
        admit(tmp_path, 'summary.txt', b'Synthetic durable admission.')
    monkeypatch.setattr(uploads, '_publish_entry', real)
    rows = entries(tmp_path)
    assert len(rows) == 1
    assert (tmp_path / rows[0]['path']).read_bytes() == b'Synthetic durable admission.'


@pytest.mark.skipif(os.name != 'nt', reason='Windows extended path spelling')
def test_windows_extended_path_spelling_keeps_containment(tmp_path, monkeypatch):
    original = Path.resolve
    def resolve(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if '.knowledge_uploads' in str(path) and not str(result).startswith(chr(92) * 2 + '?'):
            return Path(chr(92) * 2 + '?' + chr(92) + str(result))
        return result
    monkeypatch.setattr(Path, 'resolve', resolve)
    doc = admit(tmp_path, 'summary.txt', b'Synthetic extended path.')['document']
    assert (tmp_path / doc['path']).read_bytes() == b'Synthetic extended path.'


def test_crash_after_quarantine_link_can_finish_repair(tmp_path, monkeypatch):
    from selfos.storage import uploads
    raw = b'Synthetic stable original.'
    doc = admit(tmp_path, 'summary.txt', raw)['document']
    original = tmp_path / doc['path']
    original.write_bytes(b'Modified bytes to retain.')
    real_link = uploads.os.link
    def link(source, target):
        real_link(source, target)
        if 'quarantine' in str(target):
            raise OSError('Synthetic crash after quarantine preservation')
    monkeypatch.setattr(uploads.os, 'link', link)
    with pytest.raises(OSError):
        admit(tmp_path, 'summary.txt', raw)
    monkeypatch.setattr(uploads.os, 'link', real_link)
    assert len(entries(tmp_path)) == 1
    assert original.read_bytes() == raw
    assert any(p.read_bytes() == b'Modified bytes to retain.' for p in (tmp_path / '.knowledge_uploads/quarantine').iterdir())


def test_duplicate_is_allowed_when_original_storage_is_full(tmp_path, monkeypatch):
    from selfos.storage import uploads
    raw = b'Synthetic full-storage duplicate.'
    first = admit(tmp_path, 'summary.txt', raw)['document']
    monkeypatch.setattr(uploads, 'MAX_STORAGE', len(raw))
    assert admit(tmp_path, 'copy.md', raw)['document']['id'] == first['id']
    with pytest.raises(ValueError, match='storage limit'):
        admit(tmp_path, 'other.txt', b'Other content.')


def test_failed_transfer_cleans_only_its_own_temp_with_pending_admission(tmp_path, monkeypatch):
    from selfos.storage import uploads
    from selfos.sources.upload_admission import admit_document
    def fail(*args):
        raise OSError('Synthetic publication failure')
    monkeypatch.setattr(uploads, '_publish_entry', fail)
    with pytest.raises(OSError):
        admit(tmp_path, 'pending.txt', b'Synthetic pending content.')
    incoming = tmp_path / '.knowledge_uploads/incoming'
    owned = list(incoming.iterdir())
    assert len(owned) == 1
    with pytest.raises(ValueError, match='Incomplete'):
        admit_document(tmp_path, 'short.txt', io.BytesIO(b'Short'), 100)
    assert list(incoming.iterdir()) == owned
