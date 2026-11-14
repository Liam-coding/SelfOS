"""Explicit bounded native previews feeding the existing organizer and canonical caches."""
import copy
import hashlib
import re
import uuid

from selfos.sources.selection import load_sources
from selfos.storage.settings import load_settings
from selfos.knowledge.settings import limits, policy_hash
from selfos.knowledge.identity import digest
from selfos.storage.harness_scans import advance_scan, acknowledge_scan, native_parts, restart_scan
from selfos.storage.onboarding import read_metadata, write_metadata
from selfos.app.knowledge_status import _state
from selfos.sources.adapters import verified_inputs

PREVIEW_BYTES = 2 * 1024 * 1024


def _key(session, aliases=None):
    project = (aliases or {}).get(session['project_id'], session['project_id'])
    return digest([project, session['session_id'], session['part']])


def _session(session):
    return {**copy.deepcopy(session), 'partial_input': True,
            'fingerprint': digest(['onboarding-partial-v1', session['fingerprint']])}


def _receipt(session, policy, aliases=None):
    return dict(cache_key=_key(session, aliases), policy_hash=policy,
                fingerprint=hashlib.sha256((_session(session)['fingerprint'] + policy).encode()).hexdigest())


def _cached(state, receipt):
    return state.get('cache', {}).get(receipt['cache_key']) == receipt['fingerprint'] and receipt['cache_key'] in state.get('summaries', {})


def _path(identity):
    if not isinstance(identity, str) or not re.fullmatch('[a-f0-9]{32}', identity):
        raise ValueError('Invalid native preview identity')
    return '.knowledge_harness/previews/' + identity + '.json'


def prepare_native(vault, entry, *, cancel=lambda: False, restart=False):
    settings, selection = load_settings(vault), load_sources(vault)
    policy, chars = policy_hash(settings), limits(settings)['session_chars']
    if type(restart) is not bool:
        raise ValueError('Invalid new scan request')
    if restart:
        restart_scan(vault, entry, max_chars=chars)
    result = None
    # Two bounded local pages, no model work. Sealed parts always take priority.
    for _ in range(2):
        result = advance_scan(vault, entry, cancel=cancel, limits={'sessions': 2, 'messages': 40, 'page_size': 40}, max_chars=chars)
        state = _state(vault)
        aliases = state.get('project_aliases', {})
        cached = {identity:_receipt(session, policy, aliases) for identity, session in zip(result['sealed_ids'], result['sealed_sessions'])
                  if _cached(state, _receipt(session, policy, aliases))}
        if cached:
            acknowledge_scan(vault, entry, list(cached), max_chars=chars, canonical=cached)
        pending = [(identity, session) for identity, session in zip(result['sealed_ids'], result['sealed_sessions']) if identity not in cached]
        if pending or result['status'] != 'partial' or cancel():
            break
    chosen = pending[:2]
    native_parts(vault, entry, [identity for identity, _ in chosen], max_chars=chars)
    sessions = [_session(session) for _, session in chosen]
    for session in sessions:
        session['messages'] = verified_inputs(vault, session['messages'], selection)
    preview = dict(version=1, id=uuid.uuid4().hex, entry=copy.deepcopy(entry),
        sessions=sessions, part_ids=[identity for identity, _ in chosen], part_chars=chars,
        policy_hash=policy, selection_hash=digest(selection), status=result['status'],
        pending=result['pending'], diagnostics=result['diagnostics'])
    if policy != policy_hash(load_settings(vault)) or digest(selection) != digest(load_sources(vault)):
        raise ValueError('Native preview settings changed')
    write_metadata(vault, _path(preview['id']), preview, PREVIEW_BYTES)
    from selfos.storage.import_center import record_scan
    record_scan(vault, preview, 'native')
    return preview


def replay_native(vault, state, selection, incoming):
    """Rebuild retained knowledge from verified originals, never a two-part replacement."""
    from selfos.sources.adapters import verify_source
    from selfos.app.privacy import permitted_source
    candidates = [source for source in state.get('sources', {}).values()
                  if source.get('source') == 'opencode' and permitted_source(source, selection, vault)]
    candidates.extend(incoming)
    merged, total = {}, 0
    for source in candidates:
        if source['id'] in merged:
            from selfos.sources.documents import source_metadata
            source = {**source, **source_metadata(source, merged[source['id']])}
        verified = verify_source(vault, source, selection)
        if source['id'] not in merged:
            total += len(verified['text'].encode('utf-8'))
            if len(merged) >= 2000 or total > 8*1024*1024:
                raise ValueError('Native rebuild exceeds replay allowance; existing knowledge is preserved')
        merged[source['id']] = verified
    return list(merged.values())


def resolve_native(vault, identity):
    preview = read_metadata(vault, _path(identity), max_bytes=PREVIEW_BYTES)
    settings, selection = load_settings(vault), load_sources(vault)
    if (not isinstance(preview, dict) or preview.get('version') != 1 or preview.get('id') != identity
            or preview.get('policy_hash') != policy_hash(settings) or preview.get('selection_hash') != digest(selection)
            or preview.get('part_chars') != limits(settings)['session_chars']
            or not isinstance(preview.get('part_ids'), list) or len(preview['part_ids']) > 2
            or not isinstance(preview.get('sessions'), list) or len(preview['sessions']) != len(preview['part_ids'])):
        raise ValueError('Native preview is invalid or stale')
    parts = native_parts(vault, preview['entry'], preview['part_ids'], max_chars=preview['part_chars'])
    available = dict(zip(preview['part_ids'], parts))
    expected = []
    for key in preview['part_ids']:
        if not isinstance(key, str) or key not in available:
            raise ValueError('Native preview input changed; scan again')
        session = _session(available[key])
        session['messages'] = verified_inputs(vault, session['messages'], selection)
        expected.append(session)
    if expected != preview['sessions']:
        raise ValueError('Native preview material changed')
    return preview


