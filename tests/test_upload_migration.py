import base64
import hashlib
import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from selfos.app.migration import export_package, import_package
from selfos.app.uploads import upload_preview, organize_uploads
from selfos.sources.upload_admission import admit_document
from selfos.storage.uploads import get_document
from tests.test_knowledge_service import summarize, refine


def fixture(vault):
    raw = b'I prefer Chinese. We are building reliable import.'
    doc = admit_document(vault, 'Synthetic export.md', io.BytesIO(raw), len(raw))['document']
    preview = upload_preview(vault, [doc['id']])
    assert organize_uploads(vault, preview['id'], summarize=summarize, refine=refine)['installed']
    return doc, raw


@pytest.mark.parametrize('change', ['document_id', 'normalization_version', 'text_sha256', 'text_start', 'text_end', 'path', 'path_type', 'provenance'])
def test_corrupt_fragment_binding_is_rejected_before_migration_install(tmp_path, change):
    vault = tmp_path / 'source/vault'
    fixture(vault)
    bundle = export_package(vault, vault.parent, include_originals=True)
    saved = json.loads(base64.b64decode(bundle['files']['.knowledge_pipeline.json']))
    source = next(iter(saved['sources'].values()))
    source['path' if change == 'path_type' else change] = {'document_id': '0' * 64, 'normalization_version': 'unsupported-v2',
        'text_sha256': '0' * 64, 'text_start': -1, 'text_end': 999999,
        'path': '.knowledge_uploads/originals/other.txt', 'path_type': None, 'provenance': 'user_authored'}[change]
    bundle['files']['.knowledge_pipeline.json'] = base64.b64encode(json.dumps(saved).encode()).decode()
    destination = tmp_path / 'destination/vault'
    with pytest.raises(ValueError):
        import_package(destination, destination.parent, bundle)
    assert not (destination / '.knowledge_pipeline.json').exists()
    assert not list(destination.glob('.knowledge_uploads/originals/*.txt'))


def test_failed_migration_cannot_delete_concurrently_admitted_original(tmp_path, monkeypatch):
    from selfos.app import migration
    source_vault = tmp_path / 'source/vault'
    doc, raw = fixture(source_vault)
    bundle = export_package(source_vault, source_vault.parent, include_originals=True)
    destination = tmp_path / 'destination/vault'
    ready, started, finished = threading.Event(), threading.Event(), threading.Event()
    overlapped = []
    def fail_model(*args):
        ready.set()
        assert started.wait(3)
        overlapped.append(finished.wait(0.2))
        raise OSError('Synthetic migration failure after original publication')
    monkeypatch.setattr(migration, '_publish_model', fail_model)
    def admit():
        started.set()
        try:
            return admit_document(destination, 'Concurrent.md', io.BytesIO(raw), len(raw))
        finally:
            finished.set()
    with ThreadPoolExecutor(max_workers=2) as workers:
        importing = workers.submit(import_package, destination, destination.parent, bundle)
        assert ready.wait(5)
        admission = workers.submit(admit)
        with pytest.raises(OSError, match='Synthetic migration failure'):
            importing.result(timeout=5)
        admitted = admission.result(timeout=5)
    assert overlapped == [False], 'Admission must wait for migration publication and rollback'
    assert admitted['document']['id'] == doc['id']
    assert (destination / doc['path']).read_bytes() == raw
    assert get_document(destination, doc['id'])['content_sha256'] == doc['content_sha256']


@pytest.mark.parametrize('originals', [False, True])
def test_registry_and_receipts_migrate_with_optional_originals(tmp_path, originals):
    vault = tmp_path / 'source/vault'
    doc, raw = fixture(vault)
    bundle = export_package(vault, vault.parent, include_originals=originals)
    assert '.knowledge_uploads/registry/' + doc['id'] + '.json' in bundle['files']
    destination = tmp_path / 'destination/vault'
    import_package(destination, destination.parent, bundle)
    assert get_document(destination, doc['id'])['content_sha256'] == hashlib.sha256(raw).hexdigest()
    assert (destination / doc['path']).exists() is originals
    if originals:
        assert (destination / doc['path']).read_bytes() == raw
        preview = upload_preview(destination, [doc['id']])
        assert preview['sessions'] == [] and preview['cached_parts'] == 1
    else:
        repaired = admit_document(destination, 'again.md', io.BytesIO(raw), len(raw))
        assert repaired['duplicate'] and repaired['document']['id'] == doc['id']


@pytest.mark.parametrize('change', ['path', 'hash', 'original'])
def test_invalid_registry_or_original_rejected_before_install(tmp_path, change):
    vault = tmp_path / 'source/vault'
    doc, _ = fixture(vault)
    bundle = export_package(vault, vault.parent, include_originals=True)
    name = '.knowledge_uploads/registry/' + doc['id'] + '.json'
    row = json.loads(base64.b64decode(bundle['files'][name]))
    if change == 'path':
        row['path'] = '../outside.txt'
    elif change == 'hash':
        row['content_sha256'] = '0' * 64
    else:
        bundle['files'][doc['path']] = base64.b64encode(b'Modified bundled original').decode()
    bundle['files'][name] = base64.b64encode(json.dumps(row).encode()).decode()
    destination = tmp_path / 'destination/vault'
    with pytest.raises(ValueError):
        import_package(destination, destination.parent, bundle)
    assert not (destination / '.knowledge_pipeline.json').exists()
    assert not (destination / doc['path']).exists()
