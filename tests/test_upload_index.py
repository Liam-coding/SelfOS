import hashlib
import io
import json

import pytest

from selfos.sources.upload_admission import admit_document
from selfos.sources.text import redact
from selfos.sources.documents import document_source, source_metadata


def upload(vault, raw):
    return admit_document(vault, 'Synthetic description.md', io.BytesIO(raw), len(raw))['document']


def test_index_redacts_complete_document_before_fragmenting(tmp_path):
    from selfos.storage.upload_index import index_document, document_messages
    prefix = ('Synthetic project context. ' * 1000)[:23997]
    raw = (prefix + 'api_key=' + 'SyntheticSecret' * 5 + '\nPreserve durable source references.').encode()
    doc = upload(tmp_path, raw)
    result = index_document(tmp_path, doc['id'])
    messages = document_messages(tmp_path, doc['id'], result['part_ids'])
    assert messages
    assert 'SyntheticSecret' not in ''.join(m['text'] for m in messages)
    assert '[REDACTED]' in ''.join(m['text'] for m in messages)
    normalized = redact(raw.decode())
    for message in messages:
        assert message['provenance'] == 'quoted_dialogue'
        assert message['timestamp_kind'] == 'import_time'
        assert message['project_id'] == 'uploaded-document:' + doc['id']
        assert message['original_filename'] == doc['original_filename']
        assert message['text_sha256'] == hashlib.sha256(normalized.encode()).hexdigest()
        assert message['text'] == normalized[message['text_start']:message['text_end']].strip()
        metadata = source_metadata(message)
        for key in ('document_id', 'normalization_version', 'text_sha256', 'text_start', 'text_end', 'timestamp_kind'):
            assert metadata[key] == message[key]
        page = document_source(tmp_path, metadata, offset=message['text_start'])
        assert page['fragment_start'] == message['text_start']
        assert page['fragment_end'] == message['text_end']
    assert (tmp_path / doc['path']).read_bytes() == raw


def test_index_continuation_keeps_sealed_parts_and_absolute_numbers(tmp_path):
    from selfos.storage.upload_index import index_document, document_sessions
    doc = upload(tmp_path, ('Synthetic context with durable project decisions. ' * 1600).encode())
    first = index_document(tmp_path, doc['id'], max_parts=1)
    first_sessions = document_sessions(tmp_path, doc['id'], first['part_ids'])
    assert first['status'] == 'indexing' and first['cursor'] == 1
    second = index_document(tmp_path, doc['id'], max_parts=1)
    assert second['cursor'] == 2
    assert second['part_ids'][:1] == first['part_ids']
    assert document_sessions(tmp_path, doc['id'], first['part_ids']) == first_sessions
    sessions = document_sessions(tmp_path, doc['id'], second['part_ids'])
    assert [s['part'] for s in sessions] == [0, 1]
    assert len({m['id'] for s in sessions for m in s['messages']}) == sum(len(s['messages']) for s in sessions)


def test_finished_index_is_cached_without_renormalizing(tmp_path, monkeypatch):
    from selfos.storage import upload_index
    doc = upload(tmp_path, b'Synthetic project preserves immutable originals.')
    first = upload_index.index_document(tmp_path, doc['id'])
    def unexpected(*args):
        pytest.fail('Unchanged completed index must reuse normalized text')
    monkeypatch.setattr(upload_index, 'normalize_document', unexpected)
    assert upload_index.index_document(tmp_path, doc['id']) == first


def test_whitespace_document_has_no_eligible_parts(tmp_path):
    from selfos.storage.upload_index import index_document
    doc = upload(tmp_path, b' \n\t ')
    result = index_document(tmp_path, doc['id'])
    assert result['status'] == 'no_eligible_knowledge'
    assert result['part_ids'] == [] and result['cursor'] == result['total_slots']


def test_cancelled_index_preserves_previous_checkpoint(tmp_path):
    from selfos.storage.upload_index import index_document
    doc = upload(tmp_path, ('Synthetic ongoing project. ' * 2000).encode())
    first = index_document(tmp_path, doc['id'], max_parts=1)
    stopped = index_document(tmp_path, doc['id'], cancel=lambda: True)
    assert stopped['status'] == 'stopped' and stopped['cursor'] == first['cursor']
    resumed = index_document(tmp_path, doc['id'], max_parts=1)
    assert resumed['cursor'] == first['cursor'] + 1


def test_changed_original_is_rejected_even_with_cached_index(tmp_path):
    from selfos.storage.upload_index import index_document, document_sessions
    doc = upload(tmp_path, b'Synthetic immutable source.')
    indexed = index_document(tmp_path, doc['id'])
    (tmp_path / doc['path']).write_bytes(b'Externally changed source.')
    with pytest.raises(ValueError, match='changed'):
        index_document(tmp_path, doc['id'])
    with pytest.raises(ValueError, match='changed'):
        document_sessions(tmp_path, doc['id'], indexed['part_ids'])


def test_unknown_document_and_foreign_part_are_not_resolved(tmp_path):
    from selfos.storage.upload_index import index_document, document_sessions
    one = upload(tmp_path, b'Synthetic first source.')
    two = upload(tmp_path, b'Synthetic second source.')
    indexed = index_document(tmp_path, one['id'])
    index_document(tmp_path, two['id'])
    with pytest.raises(ValueError):
        document_sessions(tmp_path, two['id'], indexed['part_ids'])
    with pytest.raises(ValueError):
        index_document(tmp_path, '../outside')


def test_source_locator_rejects_unsupported_normalization(tmp_path):
    from selfos.storage.upload_index import index_document, document_messages
    doc = upload(tmp_path, b'Synthetic source locator.')
    indexed = index_document(tmp_path, doc['id'])
    message = document_messages(tmp_path, doc['id'], indexed['part_ids'])[0]
    message['normalization_version'] = 'unsupported-future-version'
    with pytest.raises(ValueError) as error:
        document_source(tmp_path, source_metadata(message))
    assert error.value.code == 'source_normalization_unavailable'


def test_corrupted_index_does_not_restart_or_return_modified_parts(tmp_path):
    from selfos.storage.upload_index import index_document, document_sessions
    doc = upload(tmp_path, b'Synthetic index integrity.')
    indexed = index_document(tmp_path, doc['id'])
    manifest = next((tmp_path / '.knowledge_uploads/index').rglob('manifest.json'))
    manifest.write_bytes(b'not JSON')
    with pytest.raises(ValueError):
        document_sessions(tmp_path, doc['id'], indexed['part_ids'])
    assert manifest.read_bytes() == b'not JSON'


def test_failure_before_cursor_publication_can_resume_same_part(tmp_path, monkeypatch):
    from selfos.storage import upload_index
    doc = upload(tmp_path, ('Synthetic durable index. ' * 1500).encode())
    real = upload_index._write_manifest
    def fail(path, value):
        if value['cursor']:
            raise OSError('Synthetic crash before cursor publication')
        return real(path, value)
    monkeypatch.setattr(upload_index, '_write_manifest', fail)
    with pytest.raises(OSError):
        upload_index.index_document(tmp_path, doc['id'], max_parts=1)
    monkeypatch.setattr(upload_index, '_write_manifest', real)
    resumed = upload_index.index_document(tmp_path, doc['id'], max_parts=1)
    assert resumed['cursor'] == 1
    assert [s['part'] for s in upload_index.document_sessions(tmp_path, doc['id'], resumed['part_ids'])] == [0]


def test_malformed_slot_metadata_is_an_actionable_error(tmp_path):
    from selfos.storage.upload_index import index_document
    doc = upload(tmp_path, b'Synthetic metadata validation.')
    index_document(tmp_path, doc['id'])
    path = next((tmp_path / '.knowledge_uploads/index').rglob('manifest.json'))
    manifest = json.loads(path.read_text(encoding='utf-8'))
    manifest['slots'] = [3]
    path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='checkpoint'):
        index_document(tmp_path, doc['id'])


def test_modified_sealed_part_is_rejected(tmp_path):
    from selfos.storage.upload_index import index_document, document_sessions
    doc = upload(tmp_path, b'Synthetic intact evidence.')
    indexed = index_document(tmp_path, doc['id'])
    path = next((tmp_path / '.knowledge_uploads/index').rglob('parts/*.json'))
    value = json.loads(path.read_text(encoding='utf-8'))
    value['messages'][0]['text'] = 'Fabricated content'
    path.write_text(json.dumps(value), encoding='utf-8')
    with pytest.raises(ValueError, match='changed'):
        document_sessions(tmp_path, doc['id'], indexed['part_ids'])
