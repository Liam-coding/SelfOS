"""Preference applicability and source-observation chronology, without I/O."""
import copy
from datetime import datetime, timezone
import re
from selfos.knowledge.temporal import instant, boundary


from selfos.knowledge.scopes import normalize_scope


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
    from selfos.knowledge.identity import normalized
    return normalized(record['key']), record['scope_type'], record['scope']


def merge_preferences(state, incoming, as_of=None):
    """Replay sourced observations so late arrivals preserve historical stages."""
    from selfos.knowledge.identity import unique, normalized
    incoming=normalize_scope(copy.deepcopy(incoming))
    selected=[normalize_scope(copy.deepcopy(old)) for old in state['preferences']
              if relation(normalize_scope(copy.deepcopy(old)))==relation(incoming)]
    historical=[normalize_scope(copy.deepcopy(old)) for old in state['records_history']
                if old.get('original_category')=='preferences' and old.get('superseded_by_source_ids')
                and relation(normalize_scope(copy.deepcopy(old)))==relation(incoming)]
    events=[]
    for record in selected+historical+[incoming]:
        supports=observations(record)
        contextual=[source for source in record['source_ids']
                    if source not in {support['source_id'] for support in supports}]
        for support in supports:
            event=copy.deepcopy(record)
            for field in ('original_category','superseded_by_source_ids','conflict','conflict_source_ids','scheduled','validity_conflict','has_future_support'):
                event.pop(field,None)
            for field in ('revision','revisions','valid_from','valid_until','validity_source_ids','validity_evidence'):
                event.pop(field,None)
            revisions=record.get('revisions') or ([record['revision']] if record.get('revision') else [])
            selected_revision=next((r for r in revisions if r['source_id']==support['source_id'] and r['evidence']==support['evidence']),None)
            if selected_revision:
                event['revision']=copy.deepcopy(selected_revision)
                event['revisions']=[copy.deepcopy(selected_revision)]
                if selected_revision.get('effective_at'):
                    event['valid_from']=selected_revision['effective_at']
                    event['validity_source_ids']=[selected_revision['source_id']]
            event.update(temporal='current', evidence=support.get('evidence',''),
                         observed_at=support.get('observed_at',''),
                         supporting_observations=[copy.deepcopy(support)],
                         source_ids=unique([support['source_id'],*contextual]),evidence_history=[])
            if event not in events:events.append(event)
    for event in events:
        revision=event.get('revision')
        if not revision or not event.get('valid_from'):continue
        for other in events:
            if (normalized(revision['previous_value'])==normalized(other['value'])
                and ordering_time(other) is not None and boundary(event['valid_from'])<=ordering_time(other)
                and observation_time(event) is not None and observation_time(other) is not None
                and observation_time(event)>observation_time(other)):
                event['validity_conflict']=True;other['validity_conflict']=True
    events.sort(key=lambda event:(ordering_time(event) is not None,
                ordering_time(event) or datetime.min.replace(tzinfo=timezone.utc),
                event['value'],event['source_ids'][0],event['evidence']))
    state['preferences']=[old for old in state['preferences']
                          if relation(normalize_scope(copy.deepcopy(old)))!=relation(incoming)]
    state['records_history']=[old for old in state['records_history'] if old not in historical]
    now=instant(as_of) if isinstance(as_of,str) else as_of or datetime.now(timezone.utc)
    for event in events:
        if event.get('valid_from') and boundary(event['valid_from'])>now:
            prior=next((r for r in reversed(state['preferences']) if relation(r)==relation(event)),None)
            if prior and normalized(prior['value'])==normalized(event['value']):
                if prior.get('scheduled'):
                    staged=copy.deepcopy(prior);staged.pop('scheduled',None)
                    temporary={'preferences':[staged],'records_history':[]}
                    _merge_current(temporary,event)
                    event=temporary['preferences'][0]
                    state['preferences'].remove(prior)
                else:
                    event['has_future_support']=True
                    _merge_current(state,event,as_of=now)
                    continue
            event['scheduled']=True
            revision=event.get('revision')
            if revision:
                for old in state['preferences']:
                    if (relation(old)==relation(event) and not old.get('scheduled') and not old.get('manual_correction')
                        and normalized(old['value'])==normalized(revision['previous_value'])):
                        if not old.get('valid_until') or boundary(event['valid_from'])<boundary(old['valid_until']):
                            old['valid_until']=event['valid_from']
                            old['validity_evidence']=revision['evidence']
                            old['validity_source_ids']=[revision['source_id']]
                        elif boundary(event['valid_from'])==boundary(old['valid_until']):
                            old['validity_source_ids']=unique(old.get('validity_source_ids',[])+[revision['source_id']])
                        old['source_ids']=unique(old['source_ids']+[revision['source_id']])
            state['preferences'].append(event)
        else:_merge_current(state,event,as_of=now)


def ordering_time(record,as_of=None):
    revisions=record.get('revisions') or ([record['revision']] if record.get('revision') else [])
    clocks={(r['source_id'],r['evidence']):boundary(r.get('effective_at')) for r in revisions}
    times=[]
    for support in observations(record):
        clock=clocks.get((support['source_id'],support.get('evidence',''))) or instant(support.get('observed_at'))
        if as_of is not None and clock is not None and clock>as_of:continue
        times.append(clock)
    return max(times) if times and all(t is not None for t in times) else None


def refresh_preferences(state,as_of=None):
    """Activate due sourced changes in a local snapshot without model calls."""
    now=instant(as_of) if isinstance(as_of,str) else as_of or datetime.now(timezone.utc)
    if not any(r.get('has_future_support') or (r.get('scheduled') and boundary(r.get('valid_from'))<=now) for r in state.get('preferences',[])):return state
    records=copy.deepcopy(state['preferences'])
    state['preferences']=[]
    state.setdefault('records_history',[])
    for record in records:merge_preferences(state,record,as_of=now)
    return state


def preference_snapshot(state,as_of=None):
    """Copy only preference state when a planned change becomes due."""
    now=instant(as_of) if isinstance(as_of,str) else as_of or datetime.now(timezone.utc)
    if not any(r.get('has_future_support') or (r.get('scheduled') and boundary(r.get('valid_from'))<=now) for r in state.get('preferences',[])):
        return state
    snapshot=dict(state)
    snapshot['preferences']=copy.deepcopy(state.get('preferences',[]))
    snapshot['records_history']=copy.deepcopy(state.get('records_history',[]))
    return refresh_preferences(snapshot,now)


def _merge_current(state, incoming, as_of=None):
    """Replace only definitely older values; preserve incomparable conflicts."""
    from selfos.knowledge.identity import normalized
    from selfos.knowledge.identity import unique
    incoming = normalize_scope(copy.deepcopy(incoming))
    current = [normalize_scope(copy.deepcopy(old)) for old in state['preferences']]
    selected = [old for old in current if relation(old) == relation(incoming) and not old.get('scheduled')]
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
        if record.get('manual_correction'):
            equal['manual_correction']=copy.deepcopy(record['manual_correction'])
        if record.get('has_future_support'):equal['has_future_support']=True
        for revision in record.get('revisions',[]):
            equal.setdefault('revisions',[])
            if revision not in equal['revisions']:equal['revisions'].append(copy.deepcopy(revision))
        if record.get('revision'):
            if record.get('valid_from'):
                known_earlier=(not equal.get('valid_from') and observation_time(equal) is not None
                               and observation_time(equal)<boundary(record['valid_from']))
                if known_earlier:
                    pass  # Existing support predates this proposed start; no continuous origin is proved.
                elif not equal.get('valid_from') or boundary(record['valid_from'])<boundary(equal['valid_from']):
                    equal['revision']=copy.deepcopy(record['revision'])
                    equal['valid_from']=record['valid_from']
                    equal['validity_source_ids']=list(record['validity_source_ids'])
                elif boundary(record['valid_from'])==boundary(equal['valid_from']):
                    equal['validity_source_ids']=unique(equal.get('validity_source_ids',[])+record['validity_source_ids'])
            elif not equal.get('revision'):equal['revision']=copy.deepcopy(record['revision'])
        if record.get('validity_conflict'):equal['validity_conflict']=True
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
        date = ordering_time(record,as_of)
        newer = [other for other in values if other is not record and date is not None
                 and ordering_time(other,as_of) is not None and ordering_time(other,as_of) > date]
        if not newer or record.get('manual_correction') or record.get('validity_conflict') or any(other.get('validity_conflict') for other in newer):
            retained.append(record)
            continue
        archived = copy.deepcopy(record)
        archived['original_category'] = 'preferences'
        archived['temporal'] = 'historical'
        archived['superseded_by_source_ids'] = sorted({item['source_id'] for other in newer
            for item in observations(other) if
            (other.get('valid_from') and boundary(other['valid_from'])>date and item['source_id'] in other.get('validity_source_ids',[]))
            or (instant(item.get('observed_at')) is not None and instant(item['observed_at'])>date)})
        explicit=[revision for other in newer for revision in other.get('revisions',[])
                  if normalized(revision['previous_value'])==normalized(record['value'])
                  and revision.get('effective_at') and boundary(revision['effective_at'])>date]
        explicit.sort(key=lambda revision:boundary(revision['effective_at']))
        if explicit:
            revision=explicit[0]
            archived['valid_until']=revision['effective_at']
            archived['validity_source_ids']=unique(archived.get('validity_source_ids',[])+[revision['source_id']])
            archived['validity_evidence']=revision['evidence']
            archived['source_ids']=unique(archived['source_ids']+[revision['source_id']])
        if archived not in state['records_history']:
            state['records_history'].append(archived)
    if len(retained) > 1:
        sources = sorted({source for record in retained for source in record['source_ids']})
        for record in retained:
            record['conflict'] = True
            record['conflict_source_ids'] = sources
    state['preferences'] = [old for old in current if relation(old) != relation(incoming) or old.get('scheduled')] + retained
