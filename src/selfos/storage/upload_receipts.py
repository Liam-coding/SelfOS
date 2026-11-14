"""Processing receipts live inside the canonical knowledge transaction."""
import copy
import re

from selfos.knowledge.identity import digest


def document_bound(source, document_id, content_hash=None):
    """A logical OpenCode message can have several admitted immutable copies."""
    if source.get('provenance') != 'quoted_dialogue':
        return False
    if source.get('source') == 'opencode':
        return any(isinstance(locator, dict) and locator.get('kind') == 'document'
                   and locator.get('document_id') == document_id
                   and (content_hash is None or locator.get('content_sha256') == content_hash)
                   for locator in source.get('source_locators', []))
    return (source.get('document_id') == document_id and
            (content_hash is None or source.get('content_sha256') == content_hash))


def prune_unbound_receipts(state):
    """Removed copy locators cannot keep claiming completion for that document."""
    for identity, receipt in list(state.get('upload_processing', {}).items()):
        receipt['parts'] = {key:part for key,part in receipt['parts'].items() if
            all(document_bound(state.get('sources', {}).get(source_id, {}), identity, part['content_sha256'])
                for source_id in part['source_ids'])}
        if not receipt['parts']:
            del state['upload_processing'][identity]


def valid_part(state, document_id, part_id, *, expected_policy_hash=None):
    receipt = state.get('upload_processing', {}).get(document_id, {})
    if not isinstance(receipt, dict) or receipt.get('version') != 1:
        return False
    part = receipt.get('parts', {}).get(part_id)
    if not isinstance(part, dict):
        return False
    if expected_policy_hash is not None and part.get('policy_hash') != expected_policy_hash:
        return False
    key = part.get('cache_key')
    if state.get('cache', {}).get(key) != part.get('fingerprint') or key not in state.get('summaries', {}):
        return False
    ids = part.get('source_ids')
    if not isinstance(ids, list) or not ids:
        return False
    return all(document_bound(state.get('sources', {}).get(identity, {}), document_id, part.get('content_sha256'))
               for identity in ids)


def add_receipts(state, sessions, policy_hash, operation_id):
    receipts = copy.deepcopy(state.get('upload_processing', {}))
    for session in sessions:
        identity, part_id = session.get('upload_document_id'), session.get('upload_part_id')
        if not identity or not part_id or not session['messages']:
            continue
        if any(not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value) for value in (identity, part_id)):
            raise ValueError('Invalid document processing identity')
        key = digest([session['project_id'], session['session_id'], session['part']])
        if state.get('cache', {}).get(key) != session['fingerprint'] or key not in state.get('summaries', {}):
            raise ValueError('Document part has no committed summary candidate')
        messages = session['messages']
        if any(m.get('document_id') != identity or m.get('provenance') != 'quoted_dialogue' for m in messages):
            raise ValueError('Invalid document processing provenance')
        receipt = receipts.setdefault(identity, {'version': 1, 'parts': {}})
        if not isinstance(receipt, dict) or receipt.get('version') != 1 or not isinstance(receipt.get('parts'), dict):
            raise ValueError('Invalid document processing receipt')
        candidate = dict(cache_key=key, fingerprint=session['fingerprint'], policy_hash=policy_hash,
            profile=session['upload_profile'], content_sha256=messages[0]['content_sha256'],
            source_ids=[m['id'] for m in messages], operation_id=operation_id)
        previous = receipt['parts'].get(part_id)
        if previous and {k:v for k,v in previous.items() if k != 'operation_id'} == {k:v for k,v in candidate.items() if k != 'operation_id'}:
            candidate = previous
        receipt['parts'][part_id] = candidate
    if receipts:
        state['upload_processing'] = receipts


def validate_receipts(state):
    receipts = state.get('upload_processing', {})
    if not isinstance(receipts, dict) or len(receipts) > 2000:
        raise ValueError('Invalid document processing receipts')
    for identity, receipt in receipts.items():
        if (not isinstance(identity, str) or not re.fullmatch('[a-f0-9]{64}', identity)
                or not isinstance(receipt, dict) or receipt.get('version') != 1
                or not isinstance(receipt.get('parts'), dict) or len(receipt['parts']) > 4096):
            raise ValueError('Invalid document processing receipt')
        for part_id, part in receipt['parts'].items():
            if (not isinstance(part_id, str) or not re.fullmatch('[a-f0-9]{64}', part_id)
                    or not isinstance(part, dict) or not isinstance(part.get('source_ids'), list)
                    or any(not isinstance(s, str) for s in part['source_ids'])
                    or any(not isinstance(part.get(field), str) or not re.fullmatch('[a-f0-9]{64}', part[field])
                           for field in ('cache_key', 'fingerprint', 'policy_hash', 'profile', 'content_sha256'))
                    or not isinstance(part.get('operation_id'), str)
                    or not re.fullmatch('[0-9]{8}T[0-9]{6}-[a-f0-9]{12}', part['operation_id'])):
                raise ValueError('Invalid document processing part receipt')
