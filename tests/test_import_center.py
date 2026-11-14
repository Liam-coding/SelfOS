"""Synthetic import observability: opening never scans or invents coverage."""
import io
import json

import pytest


def setup_sources(tmp_path):
    from selfos.sources.selection import save_sources
    root = tmp_path / 'Synthetic conversations'
    root.mkdir()
    vault = tmp_path / 'vault'
    save_sources(vault, {'roots': [str(root)], 'exclusions': []})
    return vault, root


def test_open_is_metadata_only_with_unknown_totals(tmp_path, monkeypatch):
    from selfos.app.import_center import import_center_status
    vault, root = setup_sources(tmp_path)
    monkeypatch.setattr('selfos.sources.conversations.extract_conversations',
                        lambda *a, **k: pytest.fail('Opening scanned content'))
    before = sorted(str(p) for p in vault.rglob('*'))
    result = import_center_status(vault, tmp_path)
    assert len(result['sources']) == 1
    row = result['sources'][0]
    assert row['path'] == str(root) and row['available']
    assert row['scan'] is None and row['pending_parts'] is None
    assert not result['job']['running']
    assert result['publication']['staging_is_provisional']
    assert sorted(str(p) for p in vault.rglob('*')) == before
    assert 'api_key' not in result['model']


def test_scan_receipt_survives_reload_and_invalidates_on_rules(tmp_path):
    from selfos.storage.import_center import record_scan, scan_receipts
    from selfos.app.import_center import import_center_status
    from selfos.sources.selection import load_sources, save_sources
    from selfos.knowledge.identity import digest
    from selfos.knowledge.settings import policy_hash
    from selfos.storage.settings import load_settings
    vault, root = setup_sources(tmp_path)
    preview = {'id': 'a' * 32, 'files': [{'path': str(root / 'synthetic.jsonl')}],
               'sessions': [{}, {}], 'clipped': True,
               'selection_hash': digest(load_sources(vault)),
               'policy_hash': policy_hash(load_settings(vault))}
    assert record_scan(vault, preview, 'local')
    row = import_center_status(vault, tmp_path)['sources'][0]
    assert row['scan']['selected_parts'] == 2
    assert row['scan']['coverage'] == 'bounded'
    assert row['scan']['scanned_at'] and row['pending_parts'] is None
    assert row['scan']['preview_id'] == 'a' * 32
    assert not row['scan']['committed']
    save_sources(vault, {'roots': [str(root)], 'exclusions': [str(root / 'private')]})
    assert scan_receipts(vault)['items'] == []
    assert import_center_status(vault, tmp_path)['sources'][0]['scan'] is None


def test_invalid_receipt_is_visible_and_does_not_remove_sources(tmp_path):
    from selfos.app.import_center import import_center_status
    vault, _ = setup_sources(tmp_path)
    (vault / '.knowledge_import_center.json').write_text('{broken', encoding='utf-8')
    result = import_center_status(vault, tmp_path)
    assert len(result['sources']) == 1
    assert result['diagnostics'] == ['scan_metadata_unavailable']


def test_upload_pagination_and_original_status(tmp_path):
    from selfos.app.import_center import import_center_status
    from selfos.sources.upload_admission import admit_document
    vault, _ = setup_sources(tmp_path)
    for n in range(3):
        raw = f'Synthetic project {n}. Keep traceable decisions.'.encode()
        admit_document(vault, f'Fixture {n}.md', io.BytesIO(raw), len(raw))
    result = import_center_status(vault, tmp_path, limit=2)
    assert len(result['uploads']['items']) == 2
    assert result['uploads']['has_more']
    assert all(row['status'] == 'uploaded' for row in result['uploads']['items'])
    assert all(row['processed_parts'] == 0 for row in result['uploads']['items'])
    for value in [0, 51, True, '2']:
        with pytest.raises(ValueError):
            import_center_status(vault, tmp_path, limit=value)


def test_job_and_staged_status_are_independent_of_committed(tmp_path, monkeypatch):
    from selfos.app.import_center import import_center_status
    vault, _ = setup_sources(tmp_path)
    monkeypatch.setattr('selfos.app.import_status.publication_status', lambda *a, **k:
        {'staging_is_provisional': True, 'published_operation': None,
         'operations': [{'id': 'staged', 'published': False, 'saved_sessions': 2, 'status': 'stopped'}]})
    result = import_center_status(vault, tmp_path, run={'running': True, 'phase': 'stopping',
                                                   'completed': 2, 'total': 3})
    assert result['job']['running']
    assert result['publication']['published_operation'] is None
    assert not result['publication']['operations'][0]['published']


def test_changed_policy_invalidates_receipt(tmp_path):
    from selfos.storage.import_center import record_scan, scan_receipts
    from selfos.storage.settings import load_settings, save_settings
    from selfos.knowledge.settings import policy_hash
    vault, root = setup_sources(tmp_path)
    settings = load_settings(vault)
    assert record_scan(vault, {'id': 'b'*32, 'files': [{'path': str(root/'s.jsonl')}],
                              'sessions': [], 'policy_hash': policy_hash(settings)}, 'local')
    settings['detail'] = 'detailed' if settings['detail'] != 'detailed' else 'concise'
    save_settings(vault, settings)
    assert not scan_receipts(vault)['items']


@pytest.mark.parametrize('change', [
    {'committed': True}, {'selected_parts': -1}, {'scanned_at': 'yesterday'},
    {'sources': [None]}, {'preview_id': '../outside'},
])
def test_corrupt_receipt_fields_are_diagnosed(tmp_path, change):
    from selfos.storage.import_center import record_scan, scan_receipts
    from selfos.storage.settings import load_settings
    from selfos.knowledge.settings import policy_hash
    vault, root = setup_sources(tmp_path)
    assert record_scan(vault, {'id': 'c'*32, 'files': [{'path': str(root/'s.jsonl')}],
                              'sessions': [], 'policy_hash': policy_hash(load_settings(vault))}, 'local')
    path = vault / '.knowledge_import_center.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    data['items'][0].update(change)
    path.write_text(json.dumps(data), encoding='utf-8')
    assert scan_receipts(vault)['diagnostics'] == ['scan_metadata_unavailable']


def test_missing_sources_remain_visible(tmp_path):
    from selfos.app.import_center import import_center_status
    vault, root = setup_sources(tmp_path)
    root.rmdir()
    row = import_center_status(vault, tmp_path)['sources'][0]
    assert not row['available'] and row['scan'] is None


def test_stale_preview_cannot_be_registered_as_current_scan(tmp_path):
    from selfos.storage.import_center import record_scan, scan_receipts
    from selfos.sources.selection import load_sources, save_sources
    from selfos.knowledge.identity import digest
    from selfos.knowledge.settings import policy_hash
    from selfos.storage.settings import load_settings
    vault, root = setup_sources(tmp_path)
    preview = dict(id='d'*32, files=[{'path': str(root/'s.jsonl')}], sessions=[],
                   selection_hash=digest(load_sources(vault)), policy_hash=policy_hash(load_settings(vault)))
    save_sources(vault, {'roots': [str(root)], 'exclusions': [str(root/'private')]})
    assert not record_scan(vault, preview, 'local')
    assert not scan_receipts(vault)['items']


def test_empty_local_preview_still_records_scan_time(tmp_path):
    from selfos.storage.import_center import record_scan
    from selfos.app.import_center import import_center_status
    from selfos.knowledge.settings import policy_hash
    from selfos.storage.settings import load_settings
    vault, _ = setup_sources(tmp_path)
    assert record_scan(vault, dict(id='e'*32, files=[], sessions=[],
                                 policy_hash=policy_hash(load_settings(vault))), 'local')
    assert import_center_status(vault, tmp_path)['sources'][0]['scan']['selected_parts'] == 0


def test_operation_keeps_preview_link_without_promoting_scan_to_commit(tmp_path):
    from selfos.app.import_status import RunJournal, publication_status
    from selfos.knowledge.settings import policy_hash
    from selfos.storage.settings import load_settings
    vault, _ = setup_sources(tmp_path)
    settings = load_settings(vault)
    journal = RunJournal(vault, '20261115T010000-'+'a'*12, 'incremental', 'absent', policy_hash(settings))
    journal.update(status='stopped', preview_id='f'*32, source_kind='local')
    row = publication_status(vault, {}, settings)['operations'][0]
    assert row['preview_id'] == 'f'*32 and row['source_kind'] == 'local'
    assert not row['published']


def test_native_diagnostic_and_uploaded_scan_are_retained(tmp_path):
    from selfos.storage.import_center import record_scan
    from selfos.knowledge.settings import policy_hash
    from selfos.storage.settings import load_settings
    from selfos.app.import_center import import_center_status
    vault, root = setup_sources(tmp_path)
    from selfos.sources.selection import save_sources
    database = tmp_path / 'synthetic.db'
    database.write_bytes(b'synthetic unavailable database')
    save_sources(vault, {'version': 2, 'entries': [{'kind': 'opencode_database', 'path': str(database)}], 'exclusions': []})
    assert record_scan(vault, dict(id='a'*32, entry={'path': str(database)}, sessions=[],
        policy_hash=policy_hash(load_settings(vault)), status='unsupported_schema',
        diagnostics=['unsupported_schema'], pending=False), 'native')
    scan = import_center_status(vault, tmp_path)['sources'][0]['scan']
    assert scan['status'] == 'unsupported_schema' and scan['diagnostics'] == ['unsupported_schema']


def test_corrupt_source_configuration_does_not_hide_other_sections(tmp_path):
    from selfos.app.import_center import import_center_status
    from selfos.sources.upload_admission import admit_document
    vault, _ = setup_sources(tmp_path)
    raw = b'Synthetic project decision with an original document.'
    admit_document(vault, 'Synthetic original.md', io.BytesIO(raw), len(raw))
    (vault / '.knowledge_sources.json').write_text('{broken', encoding='utf-8')
    status = import_center_status(vault, tmp_path, run={'running': True, 'phase': 'running'})
    assert status['sources'] == []
    assert 'source_metadata_unavailable' in status['diagnostics']
    assert status['job']['running']
    assert status['uploads']['items'][0]['original_filename'] == 'Synthetic original.md'
    assert status['publication']['staging_is_provisional']


def test_source_probe_error_retains_row_and_other_status(tmp_path, monkeypatch):
    from pathlib import Path
    from selfos.app.import_center import import_center_status
    vault, root = setup_sources(tmp_path)
    original = Path.is_dir
    def probe(path):
        if path == root:
            raise PermissionError('Synthetic denied location')
        return original(path)
    monkeypatch.setattr(Path, 'is_dir', probe)
    status = import_center_status(vault, tmp_path)
    assert len(status['sources']) == 1
    assert status['sources'][0]['path'] == str(root)
    assert status['sources'][0]['diagnostics'] == ['source_location_unavailable']


def test_external_scan_lock_directory_is_rejected(tmp_path):
    import os
    from selfos.storage.import_center import record_scan
    from selfos.knowledge.settings import policy_hash
    from selfos.storage.settings import load_settings
    vault, root = setup_sources(tmp_path)
    outside = tmp_path / 'outside-lock'
    outside.mkdir()
    try:
        os.symlink(outside, vault / '.knowledge_import_center', target_is_directory=True)
    except OSError as error:
        pytest.skip(f'Directory symlinks unavailable: {error}')
    preview = dict(id='a'*32, files=[{'path': str(root/'s.jsonl')}], sessions=[], policy_hash=policy_hash(load_settings(vault)))
    assert not record_scan(vault, preview, 'local')
    assert list(outside.iterdir()) == []
    assert not (vault / '.knowledge_import_center.json').exists()


def test_external_scan_lock_file_is_rejected(tmp_path):
    import os
    from selfos.storage.import_center import record_scan
    from selfos.knowledge.settings import policy_hash
    from selfos.storage.settings import load_settings
    vault, root = setup_sources(tmp_path)
    guard = vault / '.knowledge_import_center'
    guard.mkdir()
    outside = tmp_path / 'synthetic-external-lock'
    outside.write_bytes(b'unchanged synthetic external file')
    try:
        os.symlink(outside, guard / '.knowledge.lock')
    except OSError as error:
        pytest.skip(f'File symlinks unavailable: {error}')
    assert not record_scan(vault, dict(id='b'*32, files=[{'path': str(root/'s.jsonl')}],
                                      sessions=[], policy_hash=policy_hash(load_settings(vault))), 'local')
    assert outside.read_bytes() == b'unchanged synthetic external file'
