"""SelfOS-owned bounded scan checkpoints; upstream databases are never modified."""
import json
import threading
import uuid
from pathlib import Path

from selfos.storage.files import _atomic_write, _locked
from selfos.sources.selection import load_sources, allowed_database, policy_lock
from selfos.sources.opencode_records import PROFILE
from selfos.sources.opencode_database import scan_database
from selfos.sources.resumable_compaction import resume_compaction, _validate as validate_carry
from selfos.knowledge.identity import digest
from selfos.sources.compaction import part_fingerprint
from selfos.storage.settings import load_settings
from selfos.knowledge.settings import policy_hash

MAX_PAGE_BYTES = 8 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
MAX_AGGREGATE_BYTES = 128 * 1024 * 1024
_SCAN_LOCK = threading.RLock()


def _location(vault, entry, selection, max_chars):
    vault = Path(vault).resolve()
    if (not isinstance(entry, dict) or set(entry) != {'kind', 'path'}
            or entry['kind'] != 'opencode_database' or not isinstance(entry['path'], str)
            or not Path(entry['path']).is_absolute() or not allowed_database(entry['path'], selection)
            or type(max_chars) is not int or not 1 <= max_chars <= 24000):
        raise ValueError('Native scan requires an explicitly selected database')
    root = vault / '.knowledge_harness_scans'
    identity = digest([PROFILE, str(Path(entry['path']).resolve()), digest(selection), max_chars])
    path = root / (identity + '.json')
    if not root.resolve().is_relative_to(vault) or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Harness staging escapes vault')
    return root, path, identity


def _new(identity, selection, max_chars):
    return dict(version=1, identity=identity, selection_hash=digest(selection), max_chars=max_chars,
                cursor=None, snapshot=None, carry=None, sealed_sessions=[], history_sessions=[],
                canonical_receipts={}, status='partial', diagnostics=[])


def _load(path, identity, selection, max_chars):
    if not path.exists():
        return _new(identity, selection, max_chars)
    with path.open('rb') as stream:
        raw = stream.read(min(MAX_PAGE_BYTES, MAX_SNAPSHOT_BYTES) + 1)
    if len(raw) > min(MAX_PAGE_BYTES, MAX_SNAPSHOT_BYTES):
        raise ValueError('Harness checkpoint exceeds staging allowance')
    envelope = json.loads(raw)
    if (not isinstance(envelope, dict) or set(envelope) != {'state', 'sha256'}
            or envelope['sha256'] != digest(envelope['state'])):
        raise ValueError('Harness checkpoint integrity check failed')
    state = envelope['state']
    if (not isinstance(state, dict) or set(state) != set(_new(identity, selection, max_chars))
            or state['version'] != 1 or state['identity'] != identity
            or state['selection_hash'] != digest(selection) or state['max_chars'] != max_chars
            or state['status'] not in ('partial', 'complete', 'stopped', 'bounded_read')
            or not isinstance(state['sealed_sessions'], list) or not isinstance(state['diagnostics'], list)
            or not isinstance(state['history_sessions'], list) or not isinstance(state['canonical_receipts'], dict)
            or (state['cursor'] is not None and not isinstance(state['cursor'], dict))
            or (state['snapshot'] is not None and not isinstance(state['snapshot'], dict))):
        raise ValueError('Invalid durable harness checkpoint')
    if state['carry'] is not None:
        validate_carry(state['carry'], max_chars)
    for part in [*state['sealed_sessions'], *state['history_sessions']]:
        if (not isinstance(part, dict) or set(part) != {'project_id', 'session_id', 'part', 'messages', 'fingerprint'}
                or type(part['part']) is not int or part['part'] < 0 or not isinstance(part['messages'], list)
                or part['fingerprint'] != part_fingerprint(part['messages'])):
            raise ValueError('Invalid sealed harness input')
    return state


def _canonical(vault):
    path = Path(vault).resolve() / '.knowledge_pipeline.json'
    if not path.exists():
        return {}
    with path.open('rb') as stream:
        raw = stream.read(64*1024*1024 + 1)
    if len(raw) > 64*1024*1024:
        raise ValueError('Canonical knowledge exceeds native receipt validation allowance')
    state = json.loads(raw)
    if not isinstance(state, dict):
        raise ValueError('Invalid canonical knowledge')
    return state


def _receipt_valid(receipt, state, current_policy):
    return (isinstance(receipt, dict) and set(receipt) == {'cache_key', 'fingerprint', 'policy_hash'}
            and receipt['policy_hash'] == current_policy
            and isinstance(receipt['cache_key'], str) and isinstance(receipt['fingerprint'], str)
            and state.get('cache', {}).get(receipt['cache_key']) == receipt['fingerprint']
            and receipt['cache_key'] in state.get('summaries', {}))


def _restore_pending(vault, state):
    if not state['canonical_receipts']:
        return state
    canonical, current_policy = _canonical(vault), policy_hash(load_settings(vault))
    pending = {_part_id(state, part) for part in state['sealed_sessions']}
    missing = [part for part in state['history_sessions'] if _part_id(state, part) not in pending
               and not _receipt_valid(state['canonical_receipts'].get(_part_id(state, part)), canonical, current_policy)]
    return {**state, 'sealed_sessions': [*missing, *state['sealed_sessions']]}


def _publish(root, path, state):
    raw = json.dumps(dict(state=state, sha256=digest(state)), ensure_ascii=False).encode('utf-8')
    if len(raw) > min(MAX_PAGE_BYTES, MAX_SNAPSHOT_BYTES):
        return False
    total = 0
    for candidate in root.rglob('*'):
        if not candidate.resolve().is_relative_to(root.resolve()):
            raise ValueError('Harness staging contains an external path')
        if candidate.is_file() and candidate != path and candidate.name != '.knowledge.lock':
            total += candidate.stat().st_size
            if total + len(raw) > MAX_AGGREGATE_BYTES:
                return False
    if total + len(raw) > MAX_AGGREGATE_BYTES:
        return False
    _atomic_write(path, raw)
    return True


def _result(state, status=None):
    return dict(status=status or state['status'], sealed_sessions=state['sealed_sessions'],
                sealed_ids=[_part_id(state, part) for part in state['sealed_sessions']],
                cursor=state['cursor'], pending=bool(state['sealed_sessions'] or state['carry'] or state['cursor']),
                diagnostics=state['diagnostics'])


def _part_id(state, part):
    return digest([state['identity'], part['project_id'], part['session_id'], part['part'], part['fingerprint']])


def _pack(state, result, max_chars):
    carry, sealed, groups = state['carry'], [], []
    for message in result['messages']:
        if not groups or groups[-1][0]['session_id'] != message['session_id']:
            groups.append([])
        groups[-1].append(message)
    if carry is not None and groups and carry['session_id'] != groups[0][0]['session_id']:
        flushed = resume_compaction([], carry, session_end=True, max_chars=max_chars)
        sealed.extend(flushed['sealed'])
        carry = None
    active = (result['snapshot'] or {}).get('active_session')
    for index, messages in enumerate(groups):
        ended = index < len(groups)-1 or active is None or active[1] != messages[0]['session_id']
        packed = resume_compaction(messages, carry, session_end=ended, max_chars=max_chars)
        sealed.extend(packed['sealed'])
        carry = packed['carry']
    if not groups and carry is not None and (active is None or active[1] != carry['session_id']):
        flushed = resume_compaction([], carry, session_end=True, max_chars=max_chars)
        sealed.extend(flushed['sealed'])
        carry = None
    return carry, sealed


def advance_scan(vault, source_entry, *, cancel=lambda: False, limits=None, max_chars=12000):
    """Publish page, carry and cursor together; pending sealed inputs take priority."""
    with _SCAN_LOCK, policy_lock(vault):
        selection = load_sources(vault)
        root, path, identity = _location(vault, source_entry, selection, max_chars)
        with _locked(root):
            state = _load(path, identity, selection, max_chars)
            if cancel():
                return _result(state, 'stopped')
            restored = _restore_pending(vault, state)
            if restored != state:
                if not _publish(root, path, restored):
                    return _result(state, 'staging_limit')
                state = restored
            if state['sealed_sessions']:
                return _result(state)
            cursor = state['cursor'] or state['snapshot']
            result = scan_database(source_entry['path'], selection, cursor=cursor, cancel=cancel, limits=limits)
            if result['status'] not in ('partial', 'complete', 'stopped', 'bounded_read'):
                return {**_result(state, result['status']), 'diagnostics': result['diagnostics']}
            if result['snapshot'] is None:
                return _result(state, result['status'])
            try:
                carry, sealed = _pack(state, result, max_chars)
            except ValueError as error:
                if 'staging limit' not in str(error):
                    raise
                return _result(state, 'staging_limit')
            candidate = {**state, 'cursor': result['cursor'], 'snapshot': result['snapshot'],
                         'carry': carry, 'sealed_sessions': sealed, 'status': result['status'],
                         'diagnostics': result['diagnostics']}
            if not _publish(root, path, candidate):
                return _result(state, 'staging_limit')
            return _result(candidate)


def acknowledge_scan(vault, source_entry, part_ids, *, max_chars=12000, canonical=None):
    """Call only after canonical cache/knowledge publication; replay is safe before then."""
    if (not isinstance(part_ids, list) or any(not isinstance(item, str) for item in part_ids)
            or len(set(part_ids)) != len(part_ids)):
        raise ValueError('Invalid processed harness parts')
    with _SCAN_LOCK, policy_lock(vault):
        selection = load_sources(vault)
        root, path, identity = _location(vault, source_entry, selection, max_chars)
        with _locked(root):
            state = _load(path, identity, selection, max_chars)
            available = {_part_id(state, part) for part in state['sealed_sessions']}
            if set(part_ids) - available:
                raise ValueError('Processed parts do not belong to this snapshot')
            receipts = dict(state['canonical_receipts'])
            history = list(state['history_sessions'])
            if canonical is not None:
                if not isinstance(canonical, dict) or set(canonical) != set(part_ids):
                    raise ValueError('Native acknowledgement needs exact canonical receipts')
                current, current_policy = _canonical(vault), policy_hash(load_settings(vault))
                if any(not _receipt_valid(receipt, current, current_policy) for receipt in canonical.values()):
                    raise ValueError('Native parts are not canonically committed')
                receipts.update(canonical)
                historical = {_part_id(state, part) for part in history}
                history.extend(part for part in state['sealed_sessions']
                               if _part_id(state, part) in part_ids and _part_id(state, part) not in historical)
            candidate = {**state, 'sealed_sessions': [part for part in state['sealed_sessions']
                                                     if _part_id(state, part) not in part_ids],
                         'history_sessions': history, 'canonical_receipts': receipts}
            if not _publish(root, path, candidate):
                raise ValueError('Harness staging limit prevents acknowledgement')
            return _result(candidate)


def native_parts(vault, source_entry, part_ids, *, max_chars=12000):
    """Read an atomic checkpoint and verify consumed input without advancing disk state."""
    selection = load_sources(vault)
    _, path, identity = _location(vault, source_entry, selection, max_chars)
    state = _load(path, identity, selection, max_chars)
    snapshot = state['cursor'] or state['snapshot']
    if snapshot is not None:
        checked = scan_database(source_entry['path'], selection, cursor=snapshot, limits={'messages':1})
        if checked['status'] not in ('complete', 'partial'):
            raise ValueError('OpenCode scan prefix is unavailable or changed; restart the scan')
    available = {_part_id(state, part):part for part in [*state['history_sessions'], *state['sealed_sessions']]}
    if (not isinstance(part_ids, list) or any(not isinstance(key, str) or key not in available for key in part_ids)
            or len(set(part_ids)) != len(part_ids)):
        raise ValueError('Selected native parts do not belong to the retained scan')
    return [available[key] for key in part_ids]


def restart_scan(vault, source_entry, *, max_chars=12000):
    """Explicit fresh snapshot; preserve old sealed/unsealed state as a contained archive."""
    with _SCAN_LOCK, policy_lock(vault):
        selection = load_sources(vault)
        root, path, identity = _location(vault, source_entry, selection, max_chars)
        with _locked(root):
            archived = None
            if path.exists():
                with path.open('rb') as stream:
                    raw = stream.read(MAX_PAGE_BYTES + 1)
                if len(raw) > MAX_PAGE_BYTES:
                    raise ValueError('Old checkpoint exceeds archive allowance')
                archived = root / 'archive' / (uuid.uuid4().hex + '.json')
                if not archived.resolve().is_relative_to(root.resolve()) or archived.exists():
                    raise ValueError('Native scan archive escapes staging')
                _atomic_write(archived, raw)
            if not _publish(root, path, _new(identity, selection, max_chars)):
                if archived is not None:
                    archived.unlink()
                raise ValueError('Native staging allowance prevents a fresh scan')
