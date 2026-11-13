"""Synthetic pinned wire records; no upstream runtime or personal files."""
import copy
import hashlib

import pytest


def wire(tmp_path, role='user'):
    session = {'id': 'ses_synthetic', 'projectID': 'project_synthetic', 'directory': str(tmp_path / 'project')}
    info = {'id': 'msg_synthetic', 'sessionID': session['id'], 'role': role, 'time': {'created': 1700000000123}}
    parts = [{'id': 'prt_b', 'sessionID': session['id'], 'messageID': info['id'],
              'type': 'text', 'text': 'Keep immutable originals and recoverable backups.'},
             {'id': 'prt_a', 'sessionID': session['id'], 'messageID': info['id'],
              'type': 'text', 'text': 'We are building a reliable import system.'}]
    return session, {'info': info, 'parts': parts}, {'kind': 'database', 'path': str(tmp_path / 'first.db')}


def normalize(tmp_path, role='user'):
    from selfos.sources.opencode_records import normalize_record
    return normalize_record(*wire(tmp_path, role))


def test_native_record_orders_parts_retains_linkage_and_redacts_before_identity(tmp_path):
    from selfos.sources.opencode_records import normalize_record, PROFILE
    session, record, origin = wire(tmp_path)
    record['parts'][1]['text'] += ' api_key=SyntheticSecretValue'
    result = normalize_record(session, record, origin)
    assert result['source'] == 'opencode' and result['role'] == 'user'
    assert result['provenance'] == 'user_statement'
    assert result['text'].startswith('We are building') and 'SyntheticSecretValue' not in result['text']
    assert chr(10) + 'Keep immutable originals and recoverable backups.' in result['text']
    assert result['timestamp'] == '2023-11-14T22:13:20.123000Z'
    assert result['cwd'] == (tmp_path / 'project').as_posix()
    assert result['native_project_id'] == session['projectID']
    locator = result['source_locator']
    assert locator['profile'] == PROFILE and locator['version'] == 1
    assert locator['part_ids'] == ['prt_a', 'prt_b']
    assert locator['text_sha256'] == hashlib.sha256(result['text'].encode()).hexdigest()
    assert result['source_locators'] == [locator]


@pytest.mark.parametrize('change', ['role', 'time', 'nan', 'negative', 'missing_id', 'session_link', 'part_link', 'duplicate_part', 'bad_flag', 'relative_directory'])
def test_invalid_native_semantics_are_diagnosed_not_repaired(tmp_path, change):
    from selfos.sources.opencode_records import normalize_record
    session, record, origin = wire(tmp_path)
    if change == 'role': record['info']['role'] = 'system'
    elif change == 'time': record['info']['time']['created'] = True
    elif change == 'nan': record['info']['time']['created'] = float('nan')
    elif change == 'negative': record['info']['time']['created'] = -1
    elif change == 'missing_id': del record['info']['id']
    elif change == 'session_link': record['info']['sessionID'] = 'ses_other'
    elif change == 'part_link': record['parts'][0]['messageID'] = 'msg_other'
    elif change == 'duplicate_part': record['parts'].append(copy.deepcopy(record['parts'][0]))
    elif change == 'bad_flag': record['parts'][0]['synthetic'] = 'true'
    else: session['directory'] = 'relative/project'
    diagnostics = []
    assert normalize_record(session, record, origin, diagnostics=diagnostics) is None
    assert diagnostics and diagnostics[0]['code'] == 'invalid_record'
    assert 'text' not in diagnostics[0]


def test_nontext_ignored_synthetic_and_assistant_summaries_do_not_become_text(tmp_path):
    from selfos.sources.opencode_records import normalize_record
    session, record, origin = wire(tmp_path, 'assistant')
    for index, kind in enumerate(('reasoning', 'tool', 'file', 'compaction')):
        record['parts'].append({'id': f'prt_extra{index}', 'sessionID': session['id'],
            'messageID': record['info']['id'], 'type': kind, 'text': 'UnrelatedSecret'})
    record['parts'][0]['ignored'] = True
    record['parts'].append({**record['parts'][1], 'id': 'prt_synthetic', 'synthetic': True, 'text': 'UnrelatedSecret'})
    result = normalize_record(session, record, origin)
    assert result['provenance'] == 'assistant_suggestion'
    assert result['source_locator']['part_ids'] == ['prt_a']
    assert 'UnrelatedSecret' not in result['text']
    record['info']['summary'] = True
    assert normalize_record(session, record, origin) is None


@pytest.mark.parametrize('text', ['ping', '<environment_context>Runtime instructions</environment_context>',
    'This session is being continued from a previous conversation with a synthetic summary.'])
def test_existing_transient_and_runtime_filtering_is_reused(tmp_path, text):
    from selfos.sources.opencode_records import normalize_record
    session, record, origin = wire(tmp_path)
    record['parts'] = [{**record['parts'][0], 'text': text}]
    assert normalize_record(session, record, origin) is None


def test_unknown_directory_has_native_scoped_identity_and_neutral_title(tmp_path):
    from selfos.sources.opencode_records import normalize_record
    session, record, origin = wire(tmp_path)
    del session['directory']
    result = normalize_record(session, record, origin)
    assert result['project_id'] == 'opencode-project:project_synthetic'
    assert result['project'] == 'OpenCode project' and result['cwd'] == ''


def test_database_path_copies_deduplicate_but_native_message_ids_remain_distinct(tmp_path):
    from selfos.sources.opencode_records import normalize_record, merge_records
    session, record, origin = wire(tmp_path)
    first = normalize_record(session, record, origin)
    second = normalize_record(session, record, {**origin, 'path': str(tmp_path / 'copy.db')})
    assert first['id'] == second['id']
    merged = merge_records([first, second, first])
    assert len(merged) == 1 and len(merged[0]['source_locators']) == 2
    record['info']['id'] = 'msg_other'
    for part in record['parts']: part['messageID'] = 'msg_other'
    third = normalize_record(session, record, origin)
    assert third['id'] != first['id'] and len(merge_records([first, third])) == 2


def test_export_user_provenance_stays_quoted_and_separate_from_database(tmp_path):
    from selfos.sources.opencode_records import normalize_record, merge_records
    session, record, origin = wire(tmp_path)
    database = normalize_record(session, record, origin)
    document = {'kind': 'document', 'path': str(tmp_path / 'vault/.knowledge_uploads/originals' / ('a' * 64 + '.txt')),
        'document_id': 'a' * 64, 'content_sha256': 'b' * 64, 'original_filename': 'export.json'}
    exported = normalize_record(session, record, document)
    assert exported['role'] == 'user' and exported['provenance'] == 'quoted_dialogue'
    assert exported['id'] != database['id']
    assert len(merge_records([database, exported])) == 2


def test_metadata_conflict_preserves_both_evidence_identities(tmp_path):
    from selfos.sources.opencode_records import normalize_record, merge_records
    session, record, origin = wire(tmp_path)
    first = normalize_record(session, record, origin)
    record['info']['time']['created'] += 1
    changed = normalize_record(session, record, origin)
    diagnostics = []
    assert len(merge_records([first, changed], diagnostics=diagnostics)) == 2
    assert any(row['code'] == 'metadata_conflict' for row in diagnostics)


def test_identical_copy_locators_are_bounded_without_changing_logical_identity(tmp_path):
    from selfos.sources.opencode_records import normalize_record, merge_records
    session, record, origin = wire(tmp_path)
    copies = [normalize_record(session, record, {**origin, 'path': str(tmp_path / f'copy-{index}.db')}) for index in range(10)]
    diagnostics = []
    merged = merge_records(copies, diagnostics=diagnostics)
    assert len(merged) == 1 and len(merged[0]['source_locators']) == 8
    assert merged[0]['id'] == copies[0]['id']
    assert any(row['code'] == 'locator_limit' for row in diagnostics)


def test_oversize_message_is_skipped_instead_of_truncated(tmp_path):
    from selfos.sources.opencode_records import normalize_record
    session, record, origin = wire(tmp_path)
    record['parts'][0]['text'] = 'Synthetic useful context. ' * 20000
    diagnostics = []
    assert normalize_record(session, record, origin, diagnostics=diagnostics) is None
    assert diagnostics
