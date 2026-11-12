"""Preference applicability and source-observation chronology, without I/O."""
import copy
from datetime import datetime, timezone
import re


def normalize_scope(record, session=None):
    """Keep legacy declared scopes; missing applicability remains unknown."""
    scope = record.get('scope')
    declared_type = record.get('scope_type')
    if scope is None:
        kind, identity = 'unknown', 'unknown'
    elif isinstance(scope, dict):
        if set(scope) != {'type', 'id'}:
            raise ValueError('Invalid preference scope fields')
        kind, identity = scope['type'], scope['id']
        if kind in ('global', 'unknown'):
            if identity != '':
                raise ValueError('Global/unknown scope must have an empty id')
            identity = kind
    elif isinstance(scope, str):
        identity = scope
        kind = declared_type or (scope if scope in ('global', 'unknown') else 'activity')
    else:
        raise ValueError('Invalid preference scope')
    if kind not in ('global', 'activity', 'project', 'unknown'):
        raise ValueError('Unsupported preference scope type')
    if declared_type is not None and declared_type != kind:
        raise ValueError('Conflicting preference scope type')
    if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}', identity):
        raise ValueError('Invalid preference scope id')
    if kind in ('global', 'unknown') and identity != kind:
        raise ValueError('Invalid global/unknown preference scope id')
    if kind == 'project' and session is not None:
        project = session.get('project_id')
        if identity == 'current-project' and isinstance(project, str) and project:
            identity = project
        elif identity != project:
            raise ValueError('Project scope does not match the source session')
    record['scope_type'] = kind
    record['scope'] = identity.casefold() if kind == 'activity' else identity
    return record


def instant(value):
    if not isinstance(value, str) or 'T' not in value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None


def observations(record):
    values = record.get('supporting_observations')
    if isinstance(values, list) and values:
        return copy.deepcopy(values)
    return [{'source_id': source, 'evidence': record.get('evidence', ''),
             'observed_at': record.get('observed_at', '')}
            for source in record.get('source_ids', [])]


def observation_time(record):
    dates = [instant(value.get('observed_at')) for value in observations(record)]
    # An undated supporting statement cannot be silently resolved by a dated one.
    return max(dates) if dates and all(date is not None for date in dates) else None


def relation(record):
    from selfos.knowledge.records import normalized
    return normalized(record['key']), record['scope_type'], record['scope']


def merge_preferences(state, incoming):
    """Replace only definitely older values; preserve incomparable conflicts."""
    from selfos.knowledge.records import normalized
    from selfos.knowledge.identity import unique
    incoming = normalize_scope(copy.deepcopy(incoming))
    current = [normalize_scope(copy.deepcopy(old)) for old in state['preferences']]
    selected = [old for old in current if relation(old) == relation(incoming)]
    values = []
    for record in selected + [incoming]:
        record.pop('conflict', None)
        record.pop('conflict_source_ids', None)
        supports = observations(record)
        record['supporting_observations'] = supports
        record.setdefault('evidence_history', [])
        equal = next((old for old in values if normalized(old['value']) == normalized(record['value'])), None)
        if equal is None:
            values.append(record)
            continue
        equal['source_ids'] = unique(equal['source_ids'] + record['source_ids'])
        for support in supports:
            if support not in equal['supporting_observations']:
                equal['supporting_observations'].append(support)
        dated = [(instant(item.get('observed_at')), item.get('observed_at', ''))
                 for item in equal['supporting_observations']]
        known = [(date, text) for date, text in dated if date is not None]
        if known:
            equal['observed_at'] = max(known, key=lambda item: item[0])[1]
        equal['evidence_history'] = unique(equal.get('evidence_history', []) +
            [item['evidence'] for item in equal['supporting_observations']
             if item.get('evidence') and item['evidence'] != equal.get('evidence')])
    retained = []
    for record in values:
        date = observation_time(record)
        newer = [other for other in values if other is not record and date is not None
                 and observation_time(other) is not None and observation_time(other) > date]
        if not newer:
            retained.append(record)
            continue
        archived = copy.deepcopy(record)
        archived['original_category'] = 'preferences'
        archived['temporal'] = 'historical'
        archived['superseded_by_source_ids'] = sorted({item['source_id'] for other in newer
            for item in observations(other) if instant(item.get('observed_at')) is not None
            and instant(item['observed_at']) > date})
        if archived not in state['records_history']:
            state['records_history'].append(archived)
    if len(retained) > 1:
        sources = sorted({source for record in retained for source in record['source_ids']})
        for record in retained:
            record['conflict'] = True
            record['conflict_source_ids'] = sources
    state['preferences'] = [old for old in current if relation(old) != relation(incoming)] + retained
