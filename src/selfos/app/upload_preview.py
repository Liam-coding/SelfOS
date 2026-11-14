"""Explicit, local, bounded document previews with stable selected parts."""
import json
import re
import uuid

from selfos.app.privacy import selection_hash, permitted_source
from selfos.app.knowledge_status import _state
from selfos.sources.selection import load_sources
from selfos.storage.settings import load_settings
from selfos.knowledge.settings import policy_hash, limits
from selfos.storage.uploads import get_document, upload_path, upload_root, _write
from selfos.storage.upload_index import index_document, document_sessions
from selfos.storage.upload_receipts import valid_part


def _path(vault, preview_id):
    if not isinstance(preview_id, str) or not re.fullmatch('[a-f0-9]{32}', preview_id):
        raise ValueError('Invalid document preview identity')
    return upload_path(upload_root(vault), 'previews/' + preview_id + '.json')


def build_upload_preview(vault, ids):
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 10
            or any(not isinstance(identity, str) for identity in ids) or len(set(ids)) != len(ids)):
        raise ValueError('Select between one and ten uploaded documents')
    settings, selection = load_settings(vault), load_sources(vault)
    privacy_hash = selection_hash(vault)
    parts_size = limits(settings)['session_chars']
    state = _state(vault)
    selected, documents, cached, pending = [], [], 0, 0
    for identity in ids:
        doc = get_document(vault, identity)
        if not permitted_source(doc, selection, vault):
            documents.append(dict(id=identity, status='excluded', part_ids=[]))
            continue
        indexed = index_document(vault, identity, max_parts=2, part_chars=parts_size)
        available = []
        for part_id in indexed['part_ids']:
            if valid_part(state, identity, part_id, expected_policy_hash=policy_hash(settings)):
                cached += 1
            else:
                available.append(part_id)
        pending += len(available)
        chosen = available[:max(0, 2 - len(selected))]
        sessions = document_sessions(vault, identity, chosen, part_chars=parts_size)
        selected.extend(sessions)
        documents.append(dict(id=identity, status=indexed['status'], cursor=indexed['cursor'],
                              total_slots=indexed['total_slots'], part_ids=chosen,
                              content_sha256=doc['content_sha256']))
    from selfos.app.budget import read_budget, model_identity
    allowance = read_budget(vault, vault.parent)
    preview = dict(version=1, id=uuid.uuid4().hex, selected_ids=ids, sessions=selected, documents=documents,
        cached_parts=cached, pending_parts=pending, partial_coverage=pending > len(selected)
        or any(d['status'] == 'indexing' for d in documents),
        part_chars=parts_size, policy_hash=policy_hash(settings), selection_hash=privacy_hash,
        model_identity=model_identity(vault.parent), budget_limit=min(12, allowance['max_requests']))
    if privacy_hash != selection_hash(vault) or preview['policy_hash'] != policy_hash(load_settings(vault)):
        raise ValueError('Document preview settings changed; retry')
    _write(_path(vault, preview['id']), preview)
    return preview


def resolve_upload_preview(vault, preview_id):
    with _path(vault, preview_id).open('rb') as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError('Document preview exceeds local limit')
    try:
        preview = json.loads(raw)
    except ValueError:
        raise ValueError('Invalid document preview') from None
    from selfos.app.budget import model_identity
    if (not isinstance(preview, dict) or preview.get('version') != 1 or preview.get('id') != preview_id
            or preview.get('policy_hash') != policy_hash(load_settings(vault))
            or preview.get('selection_hash') != selection_hash(vault)
            or preview.get('model_identity') != model_identity(vault.parent)
            or preview.get('part_chars') != limits(load_settings(vault))['session_chars']
            or not isinstance(preview.get('selected_ids'), list) or not 1 <= len(preview['selected_ids']) <= 10
            or any(not isinstance(identity, str) for identity in preview['selected_ids'])
            or len(set(preview['selected_ids'])) != len(preview['selected_ids'])
            or not isinstance(preview.get('documents'), list)
            or any(not isinstance(doc, dict) or doc.get('status') not in ('excluded','ready','indexing','no_eligible_knowledge')
                   or not isinstance(doc.get('part_ids'), list)
                   or any(not isinstance(identity, str) for identity in doc['part_ids'])
                   or len(set(doc['part_ids'])) != len(doc['part_ids'])
                   or len(doc['part_ids']) > 2 for doc in preview['documents'])
            or [doc.get('id') for doc in preview['documents']] != preview['selected_ids']
            or type(preview.get('budget_limit')) is not int or not 1 <= preview['budget_limit'] <= 12):
        raise ValueError('Document preview is stale or invalid; create a new preview')
    selected = []
    selection = load_sources(vault)
    for row in preview['documents']:
        doc = get_document(vault, row['id'])
        if row['status'] == 'excluded':
            if permitted_source(doc, selection, vault):
                raise ValueError('Document preview changed')
            continue
        if not permitted_source(doc, selection, vault) or row.get('content_sha256') != doc['content_sha256']:
            raise ValueError('Document preview source changed')
        selected.extend(document_sessions(vault, doc['id'], row['part_ids'], part_chars=preview['part_chars']))
    if len(selected) > 2 or selected != preview.get('sessions'):
        raise ValueError('Document preview material changed')
    return preview
