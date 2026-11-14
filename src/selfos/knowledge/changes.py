"""Conservative pure comparison of effective knowledge, never another knowledge store."""
import copy
from datetime import datetime, timezone

from selfos.knowledge.corrections import apply_corrections, _entries
from selfos.knowledge.identity import digest, normalized, record_version, resolve_project_alias
from selfos.knowledge.scopes import normalize_scope

CATEGORIES = ('projects', 'personal_facts', 'preferences', 'lessons', 'history')
SUPPORT = {'source_ids', 'supporting_source_ids', 'context_source_ids', 'supporting_observations',
           'evidence', 'evidence_history', 'observed_at', 'updated_at', 'kind', 'verified', 'support_review',
           'manual_correction', 'conflict', 'conflict_source_ids', 'correction_conflict'}
IGNORED = {'original_records', 'storage_version', 'import_run_id'}


def utc_instant(value):
    try:
        instant = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
        if not isinstance(instant, datetime) or instant.tzinfo is None:
            raise ValueError('Change comparison needs an explicit UTC instant')
        return instant.astimezone(timezone.utc)
    except (TypeError, AttributeError, ValueError):
        raise ValueError('Change comparison needs an explicit UTC instant') from None


def _category(category, record):
    original = record.get('original_category')
    return original if category == 'history' and original in CATEGORIES else category


def _semantic(record, aliases):
    result = {key:copy.deepcopy(value) for key,value in record.items() if not key.startswith('_') and key not in IGNORED}
    if isinstance(result.get('project_id'), str):
        result['project_id'] = resolve_project_alias(result['project_id'], aliases)
    if 'scope' in result or 'scope_type' in result:
        normalize_scope(result)
        if result['scope_type'] == 'project':
            result['scope'] = resolve_project_alias(result['scope'], aliases)
    for key,value in list(result.items()):
        if key.endswith('source_ids') and isinstance(value, list):
            result[key] = sorted(set(value))
        elif key == 'supporting_observations' and isinstance(value, list):
            result[key] = sorted(value, key=digest)
    return result


def _snapshot(category, record, aliases):
    semantic = _semantic(record, aliases)
    effective = _category(category, record)
    if effective in ('preferences', 'personal_facts'):
        scoped = normalize_scope(copy.deepcopy(semantic))
        relation = (effective, normalized(scoped.get('key', '')), scoped['scope_type'], scoped['scope'])
    elif effective == 'projects':
        relation = (effective, semantic.get('project_id'))
    elif effective == 'history':
        relation = (effective, semantic.get('key', ''), semantic.get('domain', ''))
    else:
        relation = (effective, semantic.get('domain', ''))
    return {'category':category, 'relation_category':effective, 'relation':relation,
            'version_id':record_version(category, record), 'fingerprint':digest([category, semantic]),
            'record':{key:copy.deepcopy(value) for key,value in record.items() if not key.startswith('_') and key not in IGNORED},
            'source_ids':sorted(set(record.get('source_ids', []))), 'semantic':semantic}


def _view(state, ledger, as_of, aliases):
    effective = apply_corrections(state, ledger, as_of=as_of)
    return [_snapshot(category, record, aliases) for category,record in _entries(effective, as_of=as_of)
            if not (category == 'preferences' and record.get('scheduled'))]


def _anchors(snapshot):
    record = snapshot['record']
    direct = record.get('supporting_source_ids', record.get('source_ids', []))
    return set(direct) | {support['source_id'] for support in record.get('supporting_observations', [])
                         if isinstance(support, dict) and isinstance(support.get('source_id'), str)}


def _payload(snapshot):
    return {key:value for key,value in snapshot['semantic'].items() if key not in SUPPORT}


def _public(snapshot):
    return {key:copy.deepcopy(value) for key,value in snapshot.items() if key not in ('semantic', 'relation')}


def compare_changes(before, after, before_ledger, after_ledger, *, as_of, operation, action_id=None):
    instant = utc_instant(as_of)
    clock = instant.isoformat().replace('+00:00', 'Z')
    aliases = {**before.get('project_aliases', {}), **after.get('project_aliases', {})}
    old, new = _view(before, before_ledger, instant, aliases), _view(after, after_ledger, instant, aliases)
    left, right, changes = set(range(len(old))), set(range(len(new))), []

    def emit(action, previous, following, reason, *, matching_reason='', owner=None):
        snapshots = [old[index] for index in previous] + [new[index] for index in following]
        if not snapshots:
            return
        records = [snapshot['record'] for snapshot in snapshots]
        changes.append({'category':snapshots[0]['relation_category'], 'action':action, 'reason':reason,
            'matching_reason':matching_reason, 'action_id':owner,
            'before':[_public(old[index]) for index in previous], 'after':[_public(new[index]) for index in following],
            'conflict':any(bool(record.get('conflict') or record.get('validity_conflict') or record.get('correction_conflict'))
                           for record in records),
            'source_ids':sorted({identity for snapshot in snapshots for identity in snapshot['source_ids']}),
            'effective_at':next((record.get('valid_from') or record.get('revision', {}).get('effective_at')
                                 for record in records if record.get('valid_from') or record.get('revision')), ''),
            'applicability':'scheduled' if any(record.get('scheduled') for record in records) else
                            'historical' if following and all(new[index]['category'] == 'history' for index in following) else 'current'})
        left.difference_update(previous)
        right.difference_update(following)

    # Unchanged snapshots cancel one-to-one, preserving duplicate records.
    for previous in sorted(left):
        following = next((index for index in sorted(right) if old[previous]['fingerprint'] == new[index]['fingerprint']), None)
        if following is not None:
            left.remove(previous)
            right.remove(following)

    before_actions = {action['id']:action for action in before_ledger.get('actions', [])}
    for action in after_ledger.get('actions', []):
        identity = action['id']
        earlier = before_actions.get(identity)
        was_active, active = bool(earlier and earlier.get('active', True)), action.get('active', True)
        if was_active == active:
            continue
        originals = set(action.get('versions', []))
        anchors = {source for record in action.get('originals', []) for source in record.get('source_ids', [])}
        def owned(snapshot):
            return snapshot['record'].get('manual_correction', {}).get('action_id') == identity
        def original(snapshot):
            return snapshot['version_id'] in originals or (snapshot['relation_category'] == action['category']
                    and bool(_anchors(snapshot) & anchors) and not owned(snapshot))
        previous = [index for index in sorted(left) if original(old[index]) if active] if active else [
            index for index in sorted(left) if owned(old[index])]
        following = [index for index in sorted(right) if owned(new[index])] if active else [
            index for index in sorted(right) if original(new[index])]
        if active:
            kind = 'removed' if action['action'] == 'delete' else 'merged' if action['action'] == 'merge' else 'updated'
            emit(kind, previous, following, {'removed':'user_deleted','merged':'user_merged','updated':'user_edited'}[kind], owner=identity)
        else:
            emit('restored', previous, following, 'user_undo', owner=identity)

    # Explicit validity/history links do not make absence a statement of falsity.
    for previous in sorted(list(left)):
        candidates = [index for index in sorted(right) if old[previous]['relation'] == new[index]['relation']
                      and bool(_anchors(old[previous]) & _anchors(new[index]))
                      and new[index]['category'] == 'history']
        if len(candidates) != 1:
            continue
        following = candidates[0]
        record = new[following]['record']
        if record.get('status') == 'invalidated' and (record.get('invalidated_reason') or record.get('validity_evidence')):
            emit('invalidated', [previous], [following], record.get('invalidated_reason') or record['validity_evidence'])
        elif record.get('superseded_by_source_ids') and not record.get('scheduled'):
            emit('superseded', [previous], [following], 'explicit_supersession')

    # Equal claims with unique support replacements are updates, not fuzzy matches.
    for previous in sorted(list(left)):
        candidates = [index for index in sorted(right) if old[previous]['relation'] == new[index]['relation']
                      and _payload(old[previous]) == _payload(new[index]) and old[previous]['category'] == new[index]['category']]
        if len(candidates) != 1:
            continue
        following = candidates[0]
        if sum(old[index]['relation'] == new[following]['relation'] and _payload(old[index]) == _payload(new[following])
               and old[index]['category'] == new[following]['category'] for index in left) != 1:
            continue
        a, b = _anchors(old[previous]), _anchors(new[following])
        reason = 'support_added' if a < b else 'support_changed' if a != b else 'metadata_changed'
        emit('updated', [previous], [following], reason)

    edges = {previous:[following for following in sorted(right) if old[previous]['relation'] == new[following]['relation']
                      and bool(_anchors(old[previous]) & _anchors(new[following]))] for previous in sorted(left)}
    ambiguous_left, ambiguous_right = set(), set()
    for previous,candidates in edges.items():
        if len(candidates) != 1:
            if candidates:
                ambiguous_left.add(previous)
                ambiguous_right.update(candidates)
            continue
        following = candidates[0]
        predecessors = [index for index,values in edges.items() if following in values]
        if len(predecessors) != 1:
            ambiguous_left.update(predecessors)
            ambiguous_right.add(following)
            continue
        emit('updated', [previous], [following], 'source_lineage')

    for previous in sorted(left):
        reason = 'retention_policy_changed' if before.get('policy_hash') != after.get('policy_hash') else 'not_retained'
        emit('removed', [previous], [], reason, matching_reason='ambiguous_lineage' if previous in ambiguous_left else 'unlinked')
    for following in sorted(right):
        emit('added', [], [following], 'new_claim', matching_reason='ambiguous_lineage' if following in ambiguous_right else 'unlinked')
    changes.sort(key=lambda change:(change['category'], change['action'], digest(change)))
    for index,change in enumerate(changes):
        change['id'] = digest([clock, operation, action_id, index, change])
    return changes
