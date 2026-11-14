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


def summary(session):
    from tests.test_project_knowledge_contract import card
    message = session['messages'][0]
    return {'project': card(project_id=session['project_id'], source_ids=[message['id']],
                            updated_at=message['timestamp'], domain='work'), 'lessons': []}


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


def test_transport_copy_paths_do_not_change_compaction_fingerprints(tmp_path):
    from selfos.sources.compaction import prepare_sessions
    path, selection, _ = create_database(tmp_path, count=1)
    other = tmp_path / 'copy.db'
    other.write_bytes(path.read_bytes())
    selection['entries'].append({'kind': 'opencode_database', 'path': str(other)})
    one = scan_database(path, selection)['messages']
    two = scan_database(other, selection)['messages']
    assert prepare_sessions(one)[0]['fingerprint'] == prepare_sessions(two)[0]['fingerprint']


def test_native_and_export_do_not_overwrite_each_others_session_cache(tmp_path):
    from selfos.sources.opencode_records import normalize_record
    from selfos.sources.opencode_export import parse_export
    from test_opencode_export import origin
    from selfos.knowledge.identity import digest
    wire = export_wire(tmp_path)
    native = normalize_record(wire['info'], wire['messages'][0], {'kind':'database', 'path':str(tmp_path/'native.db')})
    exported = parse_export(json.dumps(wire).encode(), origin(tmp_path))['messages'][0]
    assert digest([native['project_id'], native['session_id'], 0]) != digest([exported['project_id'], exported['session_id'], 0])


def test_selected_export_organizes_once_with_canonical_receipts(tmp_path, monkeypatch):
    from selfos.sources.upload_admission import admit_document
    from selfos.app.uploads import upload_preview, organize_uploads
    from selfos.app import knowledge
    from tests.test_knowledge_service import refine
    def unexpected(*args, **kwargs):
        pytest.fail('No unselected scans or redundant model calls')
    monkeypatch.setattr(knowledge, 'extract_conversations', unexpected)
    raw = json.dumps(export_wire(tmp_path)).encode()
    doc = admit_document(tmp_path, 'session.json', io.BytesIO(raw), len(raw))['document']
    preview = upload_preview(tmp_path, [doc['id']])
    result = organize_uploads(tmp_path, preview['id'], summarize=summary, refine=refine)
    assert result['installed'], result
    state = json.loads((tmp_path / '.knowledge_pipeline.json').read_text())
    assert state['upload_processing'][doc['id']]['parts']
    assert all(source['source_locators'] for source in state['sources'].values())
    assert not upload_preview(tmp_path, [doc['id']])['sessions']
    assert organize_uploads(tmp_path, preview['id'], summarize=unexpected, refine=unexpected)['model_calls'] == 0


def test_native_original_changed_during_model_call_prevents_publication(tmp_path):
    from selfos.app.knowledge import run_knowledge
    from selfos.sources.selection import save_sources
    from tests.test_knowledge_service import refine
    path, selection, _ = create_database(tmp_path, count=1)
    vault = tmp_path / 'vault'
    vault.mkdir()
    save_sources(vault, selection)
    messages = scan_database(path, selection)['messages']
    def changing(session):
        result = summary(session)
        with sqlite3.connect(path) as connection:
            connection.execute('UPDATE part SET data=? WHERE id=?',
                (json.dumps({'type': 'text', 'text': 'Altered durable decision.'}), 'prt_0000_a'))
        return result
    result = run_knowledge(vault, selected_messages=messages, summarize=changing, refine=refine)
    assert not result['installed'] and result['status'] == 'failed', result
    assert 'OpenCode' in result.get('error', ''), result
    assert not (vault / '.knowledge_pipeline.json').exists()


def test_native_selected_preview_organizes_then_undo_requeues_exact_parts(tmp_path, monkeypatch):
    from selfos.app.harness_imports import prepare_native, organize_native
    from selfos.sources.selection import save_sources
    from selfos.app.knowledge import restore_last
    from selfos.app import knowledge
    from tests.test_knowledge_service import refine
    path, selection, _ = create_database(tmp_path, count=1)
    vault = tmp_path / 'vault'
    vault.mkdir()
    save_sources(vault, selection)
    monkeypatch.setattr(knowledge, 'extract_conversations', lambda *args, **kwargs: pytest.fail('Selected native import must not scan JSONL'))
    preview = prepare_native(vault, selection['entries'][0])
    assert 0 < len(preview['sessions']) <= 2
    result = organize_native(vault, preview['id'], summarize=summary, refine=refine)
    assert result['installed'], result
    assert result['request_usage']['limit'] == 12
    assert not prepare_native(vault, selection['entries'][0])['sessions']
    restore_last(vault, result['operation_id'])
    again = prepare_native(vault, selection['entries'][0])
    assert again['part_ids'] == preview['part_ids']
    assert again['sessions'] == preview['sessions']


def test_native_source_navigation_revalidates_original_bytes(tmp_path):
    from selfos.app.library import knowledge_source
    from selfos.sources.documents import source_metadata
    from selfos.sources.selection import save_sources
    path, selection, _ = create_database(tmp_path, count=1)
    vault = tmp_path / 'vault'
    vault.mkdir()
    save_sources(vault, selection)
    message = scan_database(path, selection)['messages'][0]
    (vault / '.knowledge_pipeline.json').write_text(json.dumps({'sources':{message['id']:source_metadata(message)}}), encoding='utf-8')
    assert knowledge_source(vault, message['id'])['text'] == message['text']
    with sqlite3.connect(path) as connection:
        connection.execute('DELETE FROM message')
    with pytest.raises(ValueError):
        knowledge_source(vault, message['id'])


def test_default_one_click_includes_explicitly_selected_native_database(tmp_path, monkeypatch):
    from selfos.app.knowledge import run_knowledge
    from selfos.sources.selection import save_sources
    from selfos.app import knowledge
    from tests.test_knowledge_service import refine
    path, selection, _ = create_database(tmp_path, count=1)
    vault = tmp_path/'vault'
    vault.mkdir()
    save_sources(vault, selection)
    monkeypatch.setattr(knowledge, 'extract_conversations', lambda *args, **kwargs: [])
    result = run_knowledge(vault, summarize=summary, refine=refine)
    assert result['installed'], result
    state = json.loads((vault/'.knowledge_pipeline.json').read_text())
    assert state['sources'] and all(source['source']=='opencode' for source in state['sources'].values())


def test_export_migration_preserves_source_navigation_and_rejects_forged_locator(tmp_path):
    from selfos.sources.upload_admission import admit_document
    from selfos.app.uploads import upload_preview, organize_uploads
    from selfos.app.migration import export_package, import_package
    from selfos.app.library import knowledge_source
    from tests.test_knowledge_service import refine
    root = tmp_path / 'one'
    vault = root / 'vault'
    vault.mkdir(parents=True)
    raw = json.dumps(export_wire(tmp_path)).encode()
    doc = admit_document(vault, 'session.json', io.BytesIO(raw), len(raw))['document']
    preview = upload_preview(vault, [doc['id']])
    assert organize_uploads(vault, preview['id'], summarize=summary, refine=refine)['installed']
    package = export_package(vault, root, include_originals=True)
    destination = tmp_path / 'two' / 'vault'
    destination.mkdir(parents=True)
    import_package(destination, destination.parent, package)
    state = json.loads((destination / '.knowledge_pipeline.json').read_text())
    source_id = next(iter(state['sources']))
    assert 'immutable originals' in knowledge_source(destination, source_id)['text']
    import base64
    forged = copy.deepcopy(package)
    changed = json.loads(base64.b64decode(forged['files']['.knowledge_pipeline.json']))
    locator = next(iter(changed['sources'].values()))['source_locators'][0]
    locator['part_ids'] = ['prt_forged']
    next(iter(changed['sources'].values()))['source_locator'] = copy.deepcopy(locator)
    forged['files']['.knowledge_pipeline.json'] = base64.b64encode(json.dumps(changed).encode()).decode()
    with pytest.raises(ValueError):
        import_package(tmp_path / 'forged/vault', tmp_path / 'forged', forged)


def test_foreign_typed_database_permissions_are_retained_but_not_enabled(tmp_path):
    from selfos.app.migration import import_package
    from selfos.sources.selection import load_sources
    import os, base64
    foreign = 'posix' if os.name == 'nt' else 'nt'
    path = '/synthetic/opencode.db' if foreign == 'posix' else 'C:/synthetic/opencode.db'
    origin = '/synthetic/vault' if foreign == 'posix' else 'C:/synthetic/vault'
    selection = {'version':2, 'roots':[], 'entries':[{'kind':'opencode_database','path':path}],
                 'exclusions':[], 'project_exclusions':[]}
    package = {'format':'selfos-portable','version':1,'origin_vault':origin,'origin_platform':foreign,
               'settings':{},'files':{'.knowledge_sources.json':base64.b64encode(json.dumps(selection).encode()).decode()}}
    vault = tmp_path/'vault'
    import_package(vault, tmp_path, package)
    assert not load_sources(vault)['roots'] and load_sources(vault)['version'] == 1
    assert json.loads((vault/'.knowledge_migration.json').read_text())['unresolved_selection'] == selection


def test_foreign_native_source_metadata_is_retained_unresolved(tmp_path):
    from selfos.app.migration import import_package
    from selfos.sources.opencode_records import normalize_record, opencode_metadata
    import os, base64
    foreign = 'posix' if os.name == 'nt' else 'nt'
    path = '/synthetic/opencode.db' if foreign == 'posix' else 'C:/synthetic/opencode.db'
    wire = export_wire(tmp_path)
    message = normalize_record(wire['info'], wire['messages'][0], {'kind':'database','path':str(tmp_path/'source.db')})
    source = opencode_metadata(message)
    source['path'] = path
    source['source_locator']['path'] = path
    source['source_locators'][0]['path'] = path
    state = {'sources':{source['id']:source}}
    package = {'format':'selfos-portable','version':1,'origin_platform':foreign,'origin_vault':'',
        'files':{'.knowledge_pipeline.json':base64.b64encode(json.dumps(state).encode()).decode()}}
    vault = tmp_path/'destination'
    result = import_package(vault, tmp_path/'root', package)
    assert result['sources'][0]['status'] == 'unresolved'
    assert json.loads((vault/'.knowledge_pipeline.json').read_text())['sources'][source['id']]['path'] == path


def test_publication_keeps_only_current_matching_copy_locators(tmp_path):
    from selfos.app.knowledge import run_knowledge
    from tests.test_knowledge_service import refine
    path, selection, _ = create_database(tmp_path, count=1)
    alternate = tmp_path/'alternate.db'
    alternate.write_bytes(path.read_bytes())
    selection['entries'].append({'kind':'opencode_database','path':str(alternate)})
    messages = merge_records(scan_database(path, selection)['messages'] + scan_database(alternate, selection)['messages'])
    vault = tmp_path/'vault'
    vault.mkdir()
    from selfos.sources.selection import save_sources
    save_sources(vault, selection)
    def change_after_request(session):
        result = summary(session)
        with sqlite3.connect(path) as connection:
            connection.execute('DELETE FROM message')
        return result
    result = run_knowledge(vault, selected_messages=messages, summarize=change_after_request, refine=refine)
    assert result['installed'], result
    state = json.loads((vault/'.knowledge_pipeline.json').read_text())
    source = state['sources'][messages[0]['id']]
    assert len(source['source_locators']) == 1
    assert source['source_locator']['path'] == str(alternate).replace(chr(92), '/')
