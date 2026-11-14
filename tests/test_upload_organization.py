"""Selected document organization, canonical receipts and recovery."""
import io
import json

import pytest

from selfos.sources.upload_admission import admit_document
from selfos.storage.settings import save_settings
from selfos.sources.selection import save_sources
from selfos.app.knowledge import restore_last
from tests.test_knowledge_service import summarize, refine


def uploaded(vault, name='summary.md', suffix=''):
    raw = ('I prefer Chinese. We are building reliable import. ' + suffix).encode()
    return admit_document(vault, name, io.BytesIO(raw), len(raw))['document']


def state(vault):
    return json.loads((vault / '.knowledge_pipeline.json').read_text(encoding='utf-8'))


def unexpected(*args, **kwargs):
    pytest.fail('Unselected scans and redundant model calls are forbidden')


@pytest.mark.parametrize('malformation', ['document_type', 'part_ids_type', 'status_missing', 'duplicate_selection'])
def test_malformed_preview_is_rejected_as_validation_error(tmp_path, malformation):
    from selfos.app.uploads import upload_preview
    from selfos.app.upload_preview import resolve_upload_preview, _path
    doc = uploaded(tmp_path)
    preview = upload_preview(tmp_path, [doc['id']])
    if malformation == 'document_type':
        preview['documents'][0] = None
    elif malformation == 'part_ids_type':
        preview['documents'][0]['part_ids'] = None
    elif malformation == 'status_missing':
        del preview['documents'][0]['status']
    else:
        preview['selected_ids'] *= 2
        preview['documents'] *= 2
    _path(tmp_path, preview['id']).write_text(json.dumps(preview), encoding='utf-8')
    with pytest.raises(ValueError, match='preview'):
        resolve_upload_preview(tmp_path, preview['id'])


def test_selected_preview_and_organization_never_scan_local_harnesses(tmp_path, monkeypatch):
    from selfos.app.uploads import upload_preview, organize_uploads
    from selfos.app import knowledge
    monkeypatch.setattr(knowledge, 'extract_conversations', unexpected)
    one = uploaded(tmp_path, suffix='Selected project.')
    two = uploaded(tmp_path, 'other.md', 'Unselected project.')
    preview = upload_preview(tmp_path, [one['id']])
    assert preview['selected_ids'] == [one['id']]
    assert len(preview['sessions']) == 1 and preview['budget_limit'] <= 12
    result = organize_uploads(tmp_path, preview['id'], summarize=summarize, refine=refine)
    assert result['installed'] and result['status'] == 'completed'
    saved = state(tmp_path)
    assert {s['document_id'] for s in saved['sources'].values()} == {one['id']}
    assert two['id'] not in saved['upload_processing']
    receipt = saved['upload_processing'][one['id']]
    assert receipt['parts']
    assert all(part['operation_id'] == result['operation_id'] for part in receipt['parts'].values())


def test_repeated_organization_and_new_preview_use_committed_cache(tmp_path):
    from selfos.app.uploads import upload_preview, organize_uploads
    doc = uploaded(tmp_path)
    preview = upload_preview(tmp_path, [doc['id']])
    first = organize_uploads(tmp_path, preview['id'], summarize=summarize, refine=refine)
    assert first['installed']
    repeated = organize_uploads(tmp_path, preview['id'], summarize=unexpected, refine=unexpected)
    assert repeated['model_calls'] == 0 and repeated['status'] == 'completed'
    fresh = upload_preview(tmp_path, [doc['id']])
    assert fresh['sessions'] == [] and fresh['cached_parts'] == 1
    assert organize_uploads(tmp_path, fresh['id'], summarize=unexpected, refine=unexpected)['model_calls'] == 0


@pytest.mark.parametrize('settings', [{'detail': 'detailed'}, {'domains': ['work']}])
def test_same_fragment_profile_reprocesses_when_retention_policy_changes(tmp_path, settings):
    from selfos.app.uploads import upload_preview, organize_uploads, upload_status
    doc = uploaded(tmp_path)
    first = upload_preview(tmp_path, [doc['id']])
    assert organize_uploads(tmp_path, first['id'], summarize=summarize, refine=refine)['installed']
    save_settings(tmp_path, settings)
    assert upload_status(tmp_path)['items'][0]['processed_parts'] == 0
    fresh = upload_preview(tmp_path, [doc['id']])
    assert fresh['part_chars'] == first['part_chars']
    assert fresh['sessions'] and fresh['cached_parts'] == 0
    calls = []
    def observed(session):
        calls.append(session)
        return summarize(session)
    assert organize_uploads(tmp_path, fresh['id'], summarize=observed, refine=refine)['installed']
    assert calls
    assert upload_status(tmp_path)['items'][0]['processed_parts'] == 1


def test_uploaded_ai_description_cannot_establish_verified_personal_preference(tmp_path):
    from selfos.app.uploads import upload_preview, organize_uploads
    doc = uploaded(tmp_path)
    preview = upload_preview(tmp_path, [doc['id']])
    result = organize_uploads(tmp_path, preview['id'], summarize=summarize, refine=refine)
    assert result['installed']
    assert all(record['kind'] != 'user_fact' for record in state(tmp_path)['preferences'])
    assert any(record.get('original_category') == 'preferences' and record['kind'] == 'inference'
               for record in state(tmp_path)['records_history'])


@pytest.mark.parametrize('changed', ['privacy', 'settings', 'original'])
def test_stale_preview_is_rejected_before_model_dispatch(tmp_path, changed):
    from selfos.app.uploads import upload_preview, organize_uploads
    doc = uploaded(tmp_path)
    preview = upload_preview(tmp_path, [doc['id']])
    if changed == 'settings':
        save_settings(tmp_path, {'detail': 'concise'})
    elif changed == 'privacy':
        save_sources(tmp_path, {'roots': [], 'exclusions': [],
                               'privacy_exclusions': [str(tmp_path / '.knowledge_uploads/originals')]})
    else:
        (tmp_path / doc['path']).write_bytes(b'Changed outside original.')
    with pytest.raises(ValueError):
        organize_uploads(tmp_path, preview['id'], summarize=unexpected, refine=unexpected)
    assert not (tmp_path / '.knowledge_pipeline.json').exists()


def test_preview_excluded_original_has_no_eligible_sessions(tmp_path):
    from selfos.app.uploads import upload_preview
    doc = uploaded(tmp_path)
    save_sources(tmp_path, {'roots': [], 'exclusions': [],
                           'privacy_exclusions': [str(tmp_path / doc['path'])]})
    preview = upload_preview(tmp_path, [doc['id']])
    assert preview['sessions'] == []
    assert preview['documents'][0]['status'] == 'excluded'
    assert not list((tmp_path / '.knowledge_uploads/index').rglob('normalized.txt'))


def test_stopping_then_resuming_preserves_staged_summaries(tmp_path):
    from selfos.app.uploads import upload_preview, organize_uploads
    one = uploaded(tmp_path, suffix='First source.')
    two = uploaded(tmp_path, 'other.md', 'Second source.')
    preview = upload_preview(tmp_path, [one['id'], two['id']])
    saved = []
    cancelled = [False]
    def first(item):
        saved.append(item['session_id'])
        cancelled[0] = True
        return summarize(item)
    stopped = organize_uploads(tmp_path, preview['id'], summarize=first, refine=refine,
                               max_workers=1, cancel=lambda: cancelled[0])
    assert stopped['status'] == 'stopped'
    assert not (tmp_path / '.knowledge_pipeline.json').exists()
    calls = []
    def retry(item):
        calls.append(item['session_id'])
        return summarize(item)
    resumed = organize_uploads(tmp_path, preview['id'], summarize=retry, refine=refine, max_workers=1)
    assert resumed['installed']
    assert len(calls) == 1 and calls[0] not in saved


def test_restore_invalidates_completion_but_preserves_original(tmp_path):
    from selfos.app.uploads import upload_preview, organize_uploads, upload_status
    doc = uploaded(tmp_path)
    original = (tmp_path / doc['path']).read_bytes()
    preview = upload_preview(tmp_path, [doc['id']])
    result = organize_uploads(tmp_path, preview['id'], summarize=summarize, refine=refine)
    assert upload_status(tmp_path)['items'][0]['processed_parts'] == 1
    restore_last(tmp_path, result['operation_id'])
    assert upload_status(tmp_path)['items'][0]['processed_parts'] == 0
    assert (tmp_path / doc['path']).read_bytes() == original


def test_partial_document_continuation_preserves_previous_cache_keys(tmp_path):
    from selfos.app.uploads import upload_preview, organize_uploads
    raw = ('I prefer Chinese. We are building reliable import. ' * 2200).encode()
    doc = admit_document(tmp_path, 'large.md', io.BytesIO(raw), len(raw))['document']
    first = upload_preview(tmp_path, [doc['id']])
    assert len(first['sessions']) == 2 and first['partial_coverage']
    result = organize_uploads(tmp_path, first['id'], summarize=summarize, refine=refine)
    assert result['installed']
    old_cache = dict(state(tmp_path)['cache'])
    second = upload_preview(tmp_path, [doc['id']])
    assert [s['part'] for s in second['sessions']] == [2, 3]
    assert organize_uploads(tmp_path, second['id'], summarize=summarize, refine=refine)['installed']
    assert all(state(tmp_path)['cache'][key] == fingerprint for key, fingerprint in old_cache.items())


def test_canonical_publication_failure_does_not_publish_processing_receipt(tmp_path, monkeypatch):
    from selfos.app.uploads import upload_preview, organize_uploads, upload_status
    from selfos.storage import change_publication as pipeline
    doc = uploaded(tmp_path)
    preview = upload_preview(tmp_path, [doc['id']])
    real = pipeline.commit
    def fail(vault, *args, **kwargs):
        if vault.resolve() == tmp_path.resolve():
            raise OSError('Synthetic canonical publication failure')
        return real(vault, *args, **kwargs)
    monkeypatch.setattr(pipeline, 'commit', fail)
    result = organize_uploads(tmp_path, preview['id'], summarize=summarize, refine=refine)
    assert result['status'] == 'failed' and not result['installed']
    assert upload_status(tmp_path)['items'][0]['processed_parts'] == 0


def test_receipt_is_not_valid_without_its_committed_cache(tmp_path):
    from selfos.app.uploads import upload_preview, organize_uploads, upload_status
    doc = uploaded(tmp_path)
    preview = upload_preview(tmp_path, [doc['id']])
    assert organize_uploads(tmp_path, preview['id'], summarize=summarize, refine=refine)['installed']
    path = tmp_path / '.knowledge_pipeline.json'
    saved = state(tmp_path)
    saved['cache'] = {}
    path.write_text(json.dumps(saved), encoding='utf-8')
    assert upload_status(tmp_path)['items'][0]['processed_parts'] == 0


def test_changed_original_during_generation_aborts_publication(tmp_path):
    from selfos.app.uploads import upload_preview, organize_uploads
    doc = uploaded(tmp_path)
    preview = upload_preview(tmp_path, [doc['id']])
    def change(item):
        result = summarize(item)
        (tmp_path / doc['path']).write_bytes(b'Changed while the model was running.')
        return result
    result = organize_uploads(tmp_path, preview['id'], summarize=change, refine=refine)
    assert result['status'] == 'failed' and not result['installed']
    assert not (tmp_path / '.knowledge_pipeline.json').exists()


def test_manual_deletion_remains_suppressed_after_new_policy_organization(tmp_path):
    from selfos.app.uploads import upload_preview, organize_uploads
    from selfos.app.library import list_knowledge
    from selfos.app.corrections import correct_knowledge
    doc = uploaded(tmp_path)
    preview = upload_preview(tmp_path, [doc['id']])
    assert organize_uploads(tmp_path, preview['id'], summarize=summarize, refine=refine)['installed']
    row = next(row for row in list_knowledge(tmp_path, category='history')['items']
               if row['original_category'] == 'preferences')
    correct_knowledge(tmp_path, {'action': 'delete', 'ids': [row['id']]})
    save_settings(tmp_path, {'detail': 'concise'})
    preview = upload_preview(tmp_path, [doc['id']])
    assert organize_uploads(tmp_path, preview['id'], summarize=summarize, refine=refine)['installed']
    assert list_knowledge(tmp_path, category='preferences')['items'] == []
    assert not any(row['original_category'] == 'preferences'
                   for row in list_knowledge(tmp_path, category='history')['items'])
