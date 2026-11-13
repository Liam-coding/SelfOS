"""Verified adapter dispatch uses only synthetic local sources."""
import copy
import io
import json
import sqlite3

import pytest

from test_opencode_database import create_database
from test_opencode_export import export_wire
from selfos.sources.opencode_database import scan_database
from selfos.sources.opencode_records import merge_records


def test_metadata_preserves_adapter_identity_and_all_verified_locator_fields(tmp_path):
    from selfos.sources.documents import source_metadata
    path, selection, _ = create_database(tmp_path, count=1)
    message = scan_database(path, selection)['messages'][0]
    metadata = source_metadata(message)
    assert metadata['id'] == message['id']
    assert metadata['source_locators'] == message['source_locators']
    assert metadata['cwd'] == message['cwd']
    assert metadata['native_message_id'] == message['native_message_id']


def test_verified_resolution_uses_matching_alternate_database_copy(tmp_path):
    from selfos.sources.adapters import verify_source
    path, selection, _ = create_database(tmp_path, count=1)
    copy_path = tmp_path / 'copy.db'
    copy_path.write_bytes(path.read_bytes())
    selection['entries'].append({'kind': 'opencode_database', 'path': str(copy_path)})
    merged = merge_records(scan_database(path, selection)['messages'] + scan_database(copy_path, selection)['messages'])[0]
    with sqlite3.connect(path) as connection:
        connection.execute('UPDATE part SET data=? WHERE id=?',
            (json.dumps({'type': 'text', 'text': 'Changed durable project goal.'}), 'prt_0000_a'))
    verified = verify_source(tmp_path, merged, selection)
    assert verified['id'] == merged['id']
    assert len(verified['source_locators']) == 1
    assert verified['source_locator']['path'].replace(chr(92), '/') == str(copy_path).replace(chr(92), '/')
    selection['exclusions'] = [str(copy_path)]
    with pytest.raises(ValueError):
        verify_source(tmp_path, merged, selection)


def test_forged_text_or_semantic_metadata_is_not_accepted_from_a_valid_locator(tmp_path):
    from selfos.sources.adapters import verify_source
    path, selection, _ = create_database(tmp_path, count=1)
    message = scan_database(path, selection)['messages'][0]
    forged = copy.deepcopy(message)
    forged['text'] = 'The user prefers a made up requirement.'
    with pytest.raises(ValueError):
        verify_source(tmp_path, forged, selection)
    forged = copy.deepcopy(message)
    forged['role'] = 'assistant'
    with pytest.raises(ValueError):
        verify_source(tmp_path, forged, selection)


def test_export_metadata_and_fragment_resolution_keep_quoted_provenance(tmp_path):
    from selfos.sources.upload_admission import admit_document
    from selfos.storage.opencode_exports import read_export
    from selfos.sources.documents import source_metadata
    from selfos.sources.adapters import verify_source
    raw = json.dumps(export_wire(tmp_path)).encode()
    doc = admit_document(tmp_path, 'session.json', io.BytesIO(raw), len(raw))['document']
    message = read_export(tmp_path, doc['id'])['messages'][0]
    metadata = source_metadata(message)
    assert metadata['document_id'] == doc['id']
    assert verify_source(tmp_path, metadata, {'version': 1, 'roots': [], 'exclusions': []})['provenance'] == 'quoted_dialogue'
    fragment = {**message, 'text': message['text'][:12]}
    assert verify_source(tmp_path, fragment, {'version': 1, 'roots': [], 'exclusions': []})['id'] == message['id']
