"""Uploaded document lifecycle using the existing knowledge organizer."""
from pathlib import Path

from selfos.app.upload_preview import build_upload_preview, resolve_upload_preview
from selfos.app.knowledge import run_knowledge
from selfos.app.knowledge_status import _state
from selfos.storage.uploads import list_documents
from selfos.storage.upload_index import index_status
from selfos.storage.upload_receipts import valid_part
from selfos.storage.settings import load_settings
from selfos.knowledge.settings import limits, policy_hash


def upload_preview(vault, ids):
    return build_upload_preview(Path(vault), ids)


def organize_uploads(vault, preview_id, *, config_root=None, **kwargs):
    vault = Path(vault)
    preview = resolve_upload_preview(vault, preview_id)
    state = _state(vault)
    if all(valid_part(state, s['upload_document_id'], s['upload_part_id'], expected_policy_hash=preview['policy_hash']) for s in preview['sessions']):
        return dict(status='completed', installed=False, model_calls=0, cached=True, operation_id=None)
    from selfos.providers.knowledge import api_summarizer, api_refiner
    root = Path(config_root) if config_root is not None else vault.parent
    if kwargs.get('summarize') is None:
        kwargs['summarize'] = api_summarizer(root)
    if kwargs.get('refine') is None:
        kwargs['refine'] = api_refiner(root, cancel=kwargs.get('cancel', lambda: False))
    return run_knowledge(vault, roots=[], upload_preview_id=preview_id, **kwargs)


def upload_source(vault, identity, offset=0, limit=24000):
    from selfos.storage.uploads import get_document
    from selfos.sources.documents import document_source, SourceUnavailable
    from selfos.app.privacy import permitted_source
    from selfos.sources.selection import load_sources
    doc = get_document(vault, identity)
    if not permitted_source(doc, load_sources(vault), vault):
        raise SourceUnavailable('upload_excluded', 'This original is excluded by privacy settings')
    return dict(file=doc['original_filename'], source='uploaded_file', timestamp=doc['uploaded_at'],
                timestamp_kind='import_time', **document_source(vault, doc, offset, limit))


def upload_status(vault, offset=0, limit=50):
    page = list_documents(vault, offset, limit)
    state = _state(vault)
    settings = load_settings(vault)
    part_chars = limits(settings)['session_chars']
    for row in page['items']:
        try:
            indexed = index_status(vault, row['id'], part_chars=part_chars)
            processed = sum(valid_part(state, row['id'], identity, expected_policy_hash=policy_hash(settings)) for identity in indexed['part_ids'])
            row.update(processed_parts=processed, indexed_parts=len(indexed['part_ids']),
                       index_cursor=indexed['cursor'], total_slots=indexed['total_slots'],
                       status='committed' if indexed['status'] == 'ready' and processed == len(indexed['part_ids'])
                       else 'pending_organization' if indexed['status'] == 'ready' else indexed['status'])
        except (ValueError, OSError):
            row.update(status='original_or_index_unavailable', processed_parts=0)
    return page
