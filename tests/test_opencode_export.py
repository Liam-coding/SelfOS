"""Pinned export parsing uses synthetic WithParts objects only."""
import copy
import json
import io

import pytest


def export_wire(tmp_path):
    info = dict(id='ses_export', projectID='project_export', directory=str(tmp_path / 'project'))
    messages = [dict(info=dict(id='msg_export', sessionID=info['id'], role='user', time={'created': 1700000000123}),
        parts=[dict(id='prt_b', messageID='msg_export', sessionID=info['id'], type='text', text='Preserve provenance and backups.'),
               dict(id='prt_a', messageID='msg_export', sessionID=info['id'], type='text', text='Use immutable originals.')])]
    return dict(info=info, messages=messages)


def origin(tmp_path):
    return dict(kind='document', path=str(tmp_path / 'synthetic.json'), document_id='a'*64,
                content_sha256='b'*64, original_filename='synthetic.json')


def test_export_is_quoted_dialogue_and_native_user_identity_stays_distinct(tmp_path):
    from selfos.sources.opencode_export import parse_export
    from selfos.sources.opencode_records import normalize_record
    wire = export_wire(tmp_path)
    result = parse_export(json.dumps(wire).encode(), origin(tmp_path))
    exported = result['messages'][0]
    native = normalize_record(wire['info'], wire['messages'][0], {'kind': 'database', 'path': str(tmp_path / 'native.db')})
    assert exported['text'] == native['text']
    assert exported['provenance'] == 'quoted_dialogue' and exported['id'] != native['id']
    assert exported['source_locator']['part_ids'] == ['prt_a', 'prt_b']


@pytest.mark.parametrize('fault', ['unknown_json', 'extra_top', 'bad_role', 'missing_time', 'foreign_part',
                                 'duplicate_message', 'duplicate_part', 'oversize_info', 'oversize_part'])
def test_unknown_or_malformed_exports_are_rejected(tmp_path, fault):
    from selfos.sources.opencode_export import parse_export
    wire = export_wire(tmp_path)
    if fault == 'unknown_json':
        wire = {'arbitrary': 'not a conversation export'}
    elif fault == 'extra_top':
        wire['other'] = []
    elif fault == 'bad_role':
        wire['messages'][0]['info']['role'] = 'system'
    elif fault == 'missing_time':
        del wire['messages'][0]['info']['time']
    elif fault == 'foreign_part':
        wire['messages'][0]['parts'][0]['sessionID'] = 'ses_private'
    elif fault == 'duplicate_message':
        wire['messages'].append(copy.deepcopy(wire['messages'][0]))
    elif fault == 'duplicate_part':
        wire['messages'][0]['parts'].append(copy.deepcopy(wire['messages'][0]['parts'][0]))
    elif fault == 'oversize_info':
        wire['messages'][0]['info']['extra'] = 'x'*70000
    else:
        wire['messages'][0]['parts'][0]['text'] = 'x'*300000
    with pytest.raises(ValueError):
        parse_export(json.dumps(wire).encode(), origin(tmp_path))


def test_sanitized_export_has_no_placeholder_knowledge(tmp_path):
    from selfos.sources.opencode_export import parse_export
    wire = export_wire(tmp_path)
    wire['info']['directory'] = '[redacted:session-directory:ses_export]'
    for part in wire['messages'][0]['parts']:
        part['text'] = '[redacted:text:' + part['id'] + ']'
    result = parse_export(json.dumps(wire).encode(), origin(tmp_path))
    assert not result['messages']
    assert any(row['code'] == 'sanitized_export' for row in result['diagnostics'])


def test_utf8_bytes_count_and_duplicate_json_keys_are_bounded(tmp_path, monkeypatch):
    from selfos.sources import opencode_export as exports
    wire = export_wire(tmp_path)
    monkeypatch.setattr(exports, 'MAX_MESSAGES', 0)
    with pytest.raises(ValueError):
        exports.parse_export(json.dumps(wire).encode(), origin(tmp_path))
    with pytest.raises(ValueError):
        exports.parse_export(b'{"info":{},"info":{},"messages":[]}', origin(tmp_path))
    with pytest.raises(ValueError):
        exports.parse_export(b'\xff', origin(tmp_path))


def test_export_admission_preserves_original_and_distinguishes_plain_text_profile(tmp_path):
    from selfos.sources.upload_admission import admit_document
    from selfos.storage.opencode_exports import read_export, resolve_export
    from selfos.sources.opencode_export import EXPORT_PROFILE
    raw = json.dumps(export_wire(tmp_path)).encode()
    admitted = admit_document(tmp_path, 'session.json', io.BytesIO(raw), len(raw))
    doc = admitted['document']
    assert doc['profile'] == EXPORT_PROFILE
    assert (tmp_path / doc['path']).read_bytes() == raw
    plain = admit_document(tmp_path, 'session.txt', io.BytesIO(raw), len(raw))
    assert plain['document']['id'] != doc['id']
    assert admit_document(tmp_path, 'copy.json', io.BytesIO(raw), len(raw))['duplicate']
    message = read_export(tmp_path, doc['id'])['messages'][0]
    assert resolve_export(tmp_path, message['source_locator'])['id'] == message['id']
    (tmp_path / doc['path']).write_bytes(raw + b' ')
    with pytest.raises(ValueError):
        read_export(tmp_path, doc['id'])


def test_unknown_json_never_publishes_a_registered_original(tmp_path):
    from selfos.sources.upload_admission import admit_document
    from selfos.storage.uploads import list_documents
    raw = b'{"arbitrary":"not an OpenCode export"}'
    with pytest.raises(ValueError):
        admit_document(tmp_path, 'unknown.json', io.BytesIO(raw), len(raw))
    assert not list_documents(tmp_path)['items']


def test_selected_export_parts_use_existing_compaction_without_model_calls(tmp_path):
    from selfos.sources.upload_admission import admit_document
    from selfos.storage.opencode_exports import read_export
    from selfos.storage.upload_index import index_document, document_sessions
    from selfos.sources.compaction import prepare_sessions
    wire = export_wire(tmp_path)
    wire['messages'][0]['parts'][0]['text'] = 'Preserve independent provenance and backups. ' * 900
    raw = json.dumps(wire).encode()
    doc = admit_document(tmp_path, 'session.json', io.BytesIO(raw), len(raw))['document']
    indexed = index_document(tmp_path, doc['id'], max_parts=2, part_chars=16000)
    assert len(indexed['part_ids']) == 2
    selected = document_sessions(tmp_path, doc['id'], indexed['part_ids'][:1], part_chars=16000)
    expected = prepare_sessions(read_export(tmp_path, doc['id'])['messages'], max_chars=16000)
    assert [{key:value for key,value in session.items() if not key.startswith('upload_')}
            for session in selected] == expected[:1]
    with pytest.raises(ValueError):
        document_sessions(tmp_path, doc['id'], ['f'*64], part_chars=16000)


def test_export_verifies_the_bytes_actually_parsed_not_an_earlier_file_hash(tmp_path, monkeypatch):
    from selfos.sources.upload_admission import admit_document
    from selfos.storage import opencode_exports as exports
    raw = json.dumps(export_wire(tmp_path)).encode()
    doc = admit_document(tmp_path, 'session.json', io.BytesIO(raw), len(raw))['document']
    monkeypatch.setattr(exports, '_hash', lambda path: doc['content_sha256'])
    changed = raw.replace(b'Use immutable originals.', b'Use mutable originals!!!')
    (tmp_path / doc['path']).write_bytes(changed)
    with pytest.raises(ValueError):
        exports.read_export(tmp_path, doc['id'])


def test_export_directory_metadata_can_describe_a_foreign_platform(tmp_path):
    from selfos.sources.opencode_export import parse_export
    import os
    wire = export_wire(tmp_path)
    wire['info']['directory'] = '/synthetic/mac/project' if os.name == 'nt' else 'C:/synthetic/windows/project'
    result = parse_export(json.dumps(wire).encode(), origin(tmp_path))
    assert result['messages'][0]['cwd'] == wire['info']['directory']
