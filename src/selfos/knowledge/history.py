"""knowledge / history responsibilities."""
import copy

def state_signature(record):
    return (record.get('domain','work'),record.get('status','unknown'),tuple(record.get('blockers',[])),
            tuple(record.get('next_steps',[])),bool(record.get('verified')))


def collect_state_records(cards, *, collapse=True):
    records=[]
    for card in cards:
        if 'state_inputs' in card:
            records.extend({**copy.deepcopy(record),'domain':record.get('domain','unclassified')} for record in card['state_inputs'])
        elif 'state_records' in card:
            records.extend({**copy.deepcopy(record),'domain':record.get('domain','unclassified')} for record in card['state_records'])
        elif card.get('status') != 'unknown':
            records.append({**{key:copy.deepcopy(card.get(key,[] if key in ('blockers','next_steps','source_ids') else False))
                                for key in ('status','blockers','next_steps','verified','source_ids')},
                'observed_at':card.get('updated_at',''),'_order':card.get('_order',['',0]),'domain':card.get('domain','work'),
                'source_scope':'project_context' if 'decision_history' in card else 'session_context',
                'observed_dates':[card.get('updated_at','')]})
    records.sort(key=lambda r:(r['observed_at'],*r.get('_order',['',0])))
    distinct=[]
    for record in records:
        if record not in distinct:distinct.append(record)
    if not collapse:return distinct
    grouped=[]
    for record in distinct:
        if grouped and state_signature(grouped[-1])==state_signature(record):
            previous=grouped[-1]
            previous['source_ids']=list(dict.fromkeys(previous['source_ids']+record['source_ids']))
            previous['observed_dates']=list(dict.fromkeys(previous.get('observed_dates',[])+record.get('observed_dates',[])))
            previous['observed_at']=record['observed_at']
            previous['_order']=record.get('_order',['',0])
            if record.get('source_scope')=='project_context':previous['source_scope']='project_context'
        else:grouped.append(record)
    return grouped


def rebuild_cached_state_history(state, domains):
    """Recover session attribution from saved summaries; never rerun extraction."""
    changed=0
    known=state.get('sources',{})
    for project_id,current in state.get('cards',{}).items():
        if current.get('domain','work') not in domains:continue
        candidates=[]
        for summary in state.get('summaries',{}).values():
            snapshot=summary.get('project') if isinstance(summary,dict) else None
            if not isinstance(snapshot,dict) or snapshot.get('project_id')!=project_id:continue
            if snapshot.get('domain','work') not in domains:continue
            ids=snapshot.get('source_ids')
            if not isinstance(ids,list) or not ids or any(not isinstance(i,str) or i not in known or known[i].get('project_id')!=project_id for i in ids):continue
            if snapshot.get('status') not in ('in_progress','blocked','paused','completed','reported_complete'):continue
            if any(not isinstance(snapshot.get(field),list) or len(snapshot[field])>12 or any(not isinstance(text,str) or len(text)>2000 for text in snapshot[field]) for field in ('blockers','next_steps')):continue
            recovered=copy.deepcopy(snapshot)
            recovered.pop('state_inputs',None);recovered.pop('state_records',None)
            recovered.pop('decision_history',None)
            recovered['updated_at']=max(known[i].get('timestamp','') for i in ids)
            candidates.append(recovered)
        if not candidates:continue
        if 'state_inputs' in current:
            precise=[]
            for record in current['state_inputs']:
                if record.get('source_scope')!='session_context':continue
                recovered=any(set(record['source_ids'])==set(candidate['source_ids'])
                    and record['observed_at']==candidate['updated_at']
                    and all(record.get(field)==candidate.get(field) for field in ('status','blockers','next_steps','verified'))
                    for candidate in candidates)
                if 'domain' not in record and recovered:continue
                precise.append(record)
            if precise:candidates.append({'state_inputs':precise})
        inputs=collect_state_records(candidates,collapse=False)
        if inputs and current.get('status')!='unknown' and state_signature(inputs[-1])!=state_signature(current):
            fallback=copy.deepcopy(current)
            fallback.pop('state_inputs',None);fallback.pop('state_records',None)
            fallback['decision_history']=fallback.get('decision_history',[])
            if current.get('_state_order'):fallback['updated_at']=current['_state_order'][0]
            inputs=collect_state_records([{'state_inputs':inputs},fallback],collapse=False)
        records=collect_state_records([{'state_inputs':inputs}])
        if current.get('state_inputs')!=inputs or current.get('state_records')!=records:
            current['state_inputs']=inputs;current['state_records']=records
            changed+=1
    return changed


def history_records(state):
    history=list(state.get('history',[]))+list(state.get('records_history',[]))+list(state.get('project_observations',[]))
    for card in state.get('cards',{}).values():
        for snapshot in card.get('state_records',[])[:-1]:
            text='Earlier project state: '+snapshot['status']
            if snapshot['blockers']:text+='; blockers: '+'; '.join(snapshot['blockers'])
            if snapshot['next_steps']:text+='; next steps: '+'; '.join(snapshot['next_steps'])
            history.append({'key':card['project_id']+'.state','value':text,'text':text,
                'project_title':card.get('title',''),'kind':'inference','verified':False,
                'domain':snapshot.get('domain','unclassified'),'source_ids':snapshot['source_ids'],
                'observed_at':snapshot['observed_at'],'original_category':'project_state',
                'source_scope':snapshot.get('source_scope','project_context')})
        current=set(card.get('decisions',[]))
        lineage=card.get('decision_records',[])
        for text in card.get('decision_history',[]):
            matches=[r for r in lineage if r['text']==text] or [{}]
            for record in matches:
                domain=record.get('domain','unclassified')
                if text in current and domain in ('unclassified',card.get('domain','work')):continue
                history.append({'key':card['project_id']+'.decision','value':text,
                    'text':text,'project_title':card.get('title',''),'kind':'inference',
                    'domain':domain,'source_ids':record.get('source_ids',card.get('source_ids',[])),
                    'observed_at':record.get('observed_at',''),'original_category':'projects',
                    'source_scope':record.get('source_scope','project_context')})
    return history
