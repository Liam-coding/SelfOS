import hashlib
import json

import pytest

from selfos.app.library import knowledge_source


@pytest.fixture
def registered(tmp_path):
    vault = tmp_path / 'vault'
    path = vault / '.knowledge_uploads' / 'originals' / 'immutable.txt'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'Research report\nAtomic installation retains backups.\napi_key=privatevalue')
    source = {'source': 'uploaded_file', 'path': str(path.relative_to(vault)),
              'original_filename': 'Research report.txt', 'role': 'document',
              'content_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    state_path = vault / '.knowledge_pipeline.json'
    state_path.write_text(json.dumps({'sources': {'upload1': source}}), encoding='utf-8')
    return vault, path, source


def update_source(vault, source):
    (vault / '.knowledge_pipeline.json').write_text(json.dumps({'sources': {'upload1': source}}), encoding='utf-8')


def test_uploaded_fragment_metadata_exposes_verified_position_and_import_time(registered):
    from selfos.app.library import _sources
    from selfos.sources.text import redact
    vault, path, source = registered
    normalized = redact(path.read_text(encoding='utf-8'))
    source.update(normalization_version='redacted-text-v1', text_start=16, text_end=51,
                  text_sha256=hashlib.sha256(normalized.encode()).hexdigest(), timestamp_kind='import_time')
    update_source(vault, source)
    metadata = _sources({'sources': {'upload1': source}}, ['upload1'])[0]
    assert metadata['text_start'] == 16 and metadata['text_end'] == 51
    assert metadata['timestamp_kind'] == 'import_time'
    assert knowledge_source(vault, 'upload1', offset=metadata['text_start'])['text'].startswith('Atomic')


def test_privacy_excluded_registered_upload_is_not_read(registered, monkeypatch):
    from selfos.sources.selection import save_sources
    from selfos.app import library
    vault, path, _ = registered
    save_sources(vault, {'roots': [], 'exclusions': [], 'privacy_exclusions': [str(path)]})
    monkeypatch.setattr(library, 'document_source', lambda *args: pytest.fail('Excluded original must not be read'))
    with pytest.raises(ValueError) as error:
        knowledge_source(vault, 'upload1')
    assert error.value.code == 'source_denied'


def test_registered_text_source_is_verified_redacted_and_paginated(registered):
    vault, path, _ = registered
    original = path.read_bytes()
    first = knowledge_source(vault, 'upload1', offset=0, limit=15)
    assert first['text'] == 'Research report'
    assert first['next_offset'] == 15
    second = knowledge_source(vault, 'upload1', offset=15, limit=24000)
    assert 'Atomic installation' in second['text']
    assert 'privatevalue' not in second['text'] and '[REDACTED]' in second['text']
    assert second['file'] == 'Research report.txt' and second['next_offset'] is None
    assert 'originals' not in json.dumps(second)
    assert path.read_bytes() == original


def test_changed_original_and_missing_original_are_distinct(registered):
    vault, path, _ = registered
    path.write_bytes(b'Changed original')
    with pytest.raises(ValueError) as error:
        knowledge_source(vault, 'upload1')
    assert error.value.code == 'source_changed'
    path.unlink()
    with pytest.raises(ValueError) as error:
        knowledge_source(vault, 'upload1')
    assert error.value.code == 'source_missing'


@pytest.mark.parametrize('suffix,content,code', [
    ('.pdf', b'%PDF', 'unsupported_source_format'),
    ('.txt', b'\xff\xfe', 'source_encoding'),
])
def test_binary_or_invalid_encoding_is_explicit(registered, suffix, content, code):
    vault, path, source = registered
    target = path.with_suffix(suffix)
    target.write_bytes(content)
    source.update(path=str(target), content_sha256=hashlib.sha256(content).hexdigest())
    update_source(vault, source)
    with pytest.raises(ValueError) as error:
        knowledge_source(vault, 'upload1')
    assert error.value.code == code


def test_registered_source_cannot_escape_import_root(registered, tmp_path):
    vault, _, source = registered
    private = tmp_path / 'private.txt'
    private.write_bytes(b'PRIVATE CONTENT')
    source.update(path=str(private), content_sha256=hashlib.sha256(private.read_bytes()).hexdigest())
    update_source(vault, source)
    with pytest.raises(ValueError) as error:
        knowledge_source(vault, 'upload1')
    assert error.value.code == 'source_denied'
    assert 'PRIVATE CONTENT' not in str(error.value) and str(private) not in str(error.value)


def test_unverified_source_hash_is_not_read(registered):
    vault, _, source = registered
    source['content_sha256'] = 'not a hash'
    update_source(vault, source)
    with pytest.raises(ValueError) as error:
        knowledge_source(vault, 'upload1')
    assert error.value.code == 'source_unverified'


@pytest.mark.parametrize('kwargs', [{'offset': -1}, {'offset': True}, {'limit': 0}, {'limit': 32001}, {'offset': 99999}])
def test_bad_source_pagination_is_rejected(registered, kwargs):
    with pytest.raises(ValueError):
        knowledge_source(registered[0], 'upload1', **kwargs)


def test_oversized_source_is_bounded(registered, monkeypatch):
    monkeypatch.setattr('selfos.sources.documents.MAX_BYTES', 10)
    with pytest.raises(ValueError) as error:
        knowledge_source(registered[0], 'upload1')
    assert error.value.code == 'source_too_large'


def test_symlinked_original_cannot_escape(registered, tmp_path):
    vault, path, source = registered
    private = tmp_path / 'outside.txt'
    private.write_bytes(path.read_bytes())
    link = path.parent / 'link.txt'
    try:
        link.symlink_to(private)
    except OSError:
        pytest.skip('File symlinks unavailable in this environment')
    source['path'] = str(link)
    update_source(vault, source)
    with pytest.raises(ValueError) as error:
        knowledge_source(vault, 'upload1')
    assert error.value.code == 'source_denied'
