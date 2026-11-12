"""Pure durable user-action replay, separate from generated source evidence."""
import copy
from datetime import datetime, timezone
import uuid

from selfos.knowledge.identity import digest, normalized, unique, resolve_project_alias
from selfos.knowledge.preferences import normalize_scope
from selfos.sources.text import redact


from selfos.knowledge.identity import record_version


def _entries(state):
    for record in state.get('cards',{}).values():yield 'projects',record
    for category in ('personal_facts','preferences','lessons'):
        for record in state.get(category,[]):yield category,record
    from selfos.knowledge.history import history_records
    for record in history_records(state):yield 'history',record


def _relation(category, record):
    if category in ('preferences','personal_facts'):
        scoped=normalize_scope(copy.deepcopy(record))
        return [category,normalized(record.get('key','')),scoped['scope_type'],scoped['scope']]
    if category=='projects':return [category,record.get('project_id')]
    return [category,normalized(record.get('text',''))]


def _signatures(record):
    supports=record.get('supporting_observations',[])
    if supports:return {digest([r['source_id'],r.get('evidence','')]) for r in supports}
    return {digest([source,record.get('evidence',record.get('text',''))]) for source in record.get('source_ids',[])}


def _remove(state, record):
    state.setdefault('_correction_hidden_history',[]).append(record_version('history',record))
    for field in ('personal_facts','preferences','lessons','history','records_history'):
        state[field]=[r for r in state.get(field,[]) if r is not record and r!=record]
    for key,value in list(state.get('cards',{}).items()):
        if value is record:del state['cards'][key]


def _insert(state,category,record):
    if category=='projects':state.setdefault('cards',{})[record['project_id']]=record
    else:state.setdefault(category,[]).append(record)


def _manual(action):
    originals=action['originals']
    record=copy.deepcopy(originals[0])
    for field in ('scheduled','has_future_support','revision','revisions','valid_from','valid_until','conflict','conflict_source_ids','correction_conflict','validity_conflict'):
        record.pop(field,None)
    record.update(action.get('patch',{}))
    if 'value' in action.get('patch',{}) and 'text' not in action['patch']:
        record['text']=action['patch']['value']
    if action['category']=='projects' and 'text' in record:record['intent']=record.pop('text')
    record['kind']='user_correction'
    record['source_ids']=unique([i for r in originals for i in r.get('source_ids',[])])
    record['supporting_source_ids']=unique([i for r in originals for i in r.get('supporting_source_ids',[])])
    record['context_source_ids']=unique([i for r in originals for i in r.get('context_source_ids',[])])
    record['supporting_observations']=[]
    for original in originals:
        for support in original.get('supporting_observations',[]):
            if support not in record['supporting_observations']:record['supporting_observations'].append(copy.deepcopy(support))
    record['original_records']=copy.deepcopy(originals)
    record['manual_correction']={'action_id':action['id'],'at':action['at']}
    record['_correction_action_ids']=unique([i for r in originals for i in r.get('_correction_action_ids',[])]+[action['id']])
    return record


def _project_action(state,action):
    original=action['originals'][0]
    identity=resolve_project_alias(original['project_id'],state.get('project_aliases',{}))
    current=state.get('cards',{}).get(identity)
    original_sources=unique([source for r in action['originals'] for source in r.get('source_ids',[])])
    new_evidence=bool(current and set(current.get('source_ids',[]))-set(original_sources))
    if action['action']=='delete':
        if current and new_evidence:
            current.update(conflict=True,correction_conflict=action['id'])
        elif current:
            _remove(state,current)
        state['correction_review'].append({'action_id':action['id'],'reason':'suppressed_project_lineage','original':copy.deepcopy(original)})
        return
    manual=_manual(action)
    if current:
        for key,value in current.items():
            if key not in ('intent','kind','manual_correction','original_records','_correction_action_ids','conflict','conflict_source_ids','correction_conflict'):
                manual[key]=copy.deepcopy(value)
        manual['source_ids']=unique(list(original_sources)+current.get('source_ids',[]))
        if new_evidence and current.get('intent')!=manual.get('intent'):
            manual.update(conflict=True,conflict_source_ids=manual['source_ids'],
                          proposed_revision={'intent':current.get('intent',''),'source_ids':current.get('source_ids',[])})
    else:
        manual.update(status='unknown',verified=False,updated_at=action['at'])
        for field in ('blockers','next_steps','decisions','state_records','state_inputs','decision_records','decision_history'):
            manual[field]=[]
    manual['project_id']=identity
    _insert(state,'projects',manual)


def apply_corrections(state, ledger):
    from selfos.knowledge.preferences import preference_snapshot
    result=copy.deepcopy(preference_snapshot(state))
    result.setdefault('correction_review',[])
    for action in ledger.get('actions',[]):
        if not action.get('active',True):continue
        action=copy.deepcopy(action)
        aliases=result.get('project_aliases',{})
        if action['category'] in ('preferences','personal_facts') and len(action['relation'])==4 and action['relation'][2]=='project':
            action['relation'][3]=resolve_project_alias(action['relation'][3],aliases)
            for original in action['originals']:
                normalize_scope(original)
                original['scope']=resolve_project_alias(original['scope'],aliases)
        if action['category']=='projects':
            _project_action(result,action)
            continue
        category=action['category'];anchors=set(action['anchors']);candidates=[]
        for kind,record in list(_entries(result)):
            effective_kind=record.get('original_category',kind) if kind=='history' and category!='history' else kind
            if effective_kind!=category:continue
            matching=_signatures(record)&anchors
            if matching or record_version(kind,record) in action['versions']:
                _remove(result,record)
                if action['action']=='delete':
                    result['correction_review'].append({'action_id':action['id'],'reason':'suppressed_source_lineage',
                                                       'original':copy.deepcopy(record)})
                new=[r for r in record.get('supporting_observations',[]) if digest([r['source_id'],r.get('evidence','')]) not in anchors]
                if new:
                    candidate=copy.deepcopy(record)
                    candidate['supporting_observations']=new
                    candidate['supporting_source_ids']=unique([r['source_id'] for r in new])
                    candidate['source_ids']=unique(candidate['supporting_source_ids']+candidate.get('context_source_ids',[]))
                    candidate['evidence']=new[0]['evidence'];candidate['conflict']=True
                    candidate['correction_conflict']=action['id']
                    _insert(result,kind,candidate);candidates.append(candidate)
            elif action['action']!='delete' and _relation(effective_kind,record)==action['relation']:
                record['conflict']=True;record['correction_conflict']=action['id'];candidates.append(record)
        if action['action']!='delete':
            corrected=_manual(action)
            if candidates:
                corrected['conflict']=True
                sources=unique(corrected.get('source_ids',[])+[i for r in candidates for i in r.get('source_ids',[])])
                for r in [corrected,*candidates]:r['conflict_source_ids']=sources
            _insert(result,category,corrected)
    return result


def create_action(state, ledger, request):
    if not isinstance(request,dict):raise ValueError('Action must be an object')
    result=copy.deepcopy(ledger) if ledger else {'version':1,'actions':[]}
    if result.get('version')!=1 or not isinstance(result.get('actions'),list):raise ValueError('Unsupported correction ledger')
    operation=request.get('action')
    if operation=='undo':
        identity=request.get('action_id')
        target=next((a for a in result['actions'] if a['id']==identity and a.get('active',True)),None)
        if target is None:raise ValueError('Action unavailable')
        if any(a.get('active',True) and identity in a.get('dependencies',[]) for a in result['actions']):
            raise ValueError('Undo dependent actions first')
        target['active']=False
        target['undone_at']=datetime.now(timezone.utc).isoformat()
        return result
    if operation not in ('edit','delete','merge'):raise ValueError('Unsupported correction action')
    ids=request.get('ids')
    if not isinstance(ids,list) or not ids or len(ids)>20 or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids):
        raise ValueError('Select valid record versions')
    view=apply_corrections(state,result)
    indexed={record_version(category,record):(category,record) for category,record in _entries(view)}
    if any(i not in indexed for i in ids):raise ValueError('Record version changed; reload before correcting')
    selected=[indexed[i] for i in ids]
    category=selected[0][0]
    if any(kind!=category for kind,_ in selected):raise ValueError('Merge compatible categories only')
    if operation=='merge':
        if len(ids)<2 or category=='projects':raise ValueError('Select compatible records to merge')
        if category in ('preferences','personal_facts') and len({digest(_relation(kind,r)) for kind,r in selected})!=1:
            raise ValueError('Merge the same relation and scope only')
    elif len(ids)!=1:raise ValueError('Select one record')
    patch=request.get('patch',{})
    allowed={'text','value'} if category in ('preferences','personal_facts') else {'text'}
    if not isinstance(patch,dict) or set(patch)-allowed:raise ValueError('Only editable fields may change')
    if operation!='delete' and not patch:raise ValueError('Provide corrected content')
    clean={}
    for field,value in patch.items():
        if not isinstance(value,str) or not value.strip() or len(value)>2000:raise ValueError('Corrected content must be nonempty and short')
        clean[field]=redact(value.strip())
    originals=[copy.deepcopy(r) for _,r in selected]
    result['actions'].append({'id':uuid.uuid4().hex,'at':datetime.now(timezone.utc).isoformat(),
        'action':operation,'category':category,'active':True,'versions':ids,'patch':clean,
        'relation':_relation(category,originals[0]),'anchors':sorted(set().union(*[_signatures(r) for r in originals])),
        'originals':originals,'dependencies':unique([i for r in originals for i in r.get('_correction_action_ids',[])])})
    return result


def correction_options(state, ledger, identity=''):
    view=apply_corrections(state,ledger)
    entries=list(_entries(view))
    selected=next(((category,r) for category,r in entries if record_version(category,r)==identity),None)
    compatible=[]
    if selected:
        category,record=selected
        if category!='projects':
            for kind,candidate in entries:
                version=record_version(kind,candidate)
                if kind==category and version!=identity and (kind not in ('preferences','personal_facts') or _relation(kind,candidate)==_relation(category,record)):
                    compatible.append({'id':version,'title':redact(str(candidate.get('value') or candidate.get('text','')))})
    actions=[]
    for item in ledger.get('actions',[]):
        active=item.get('active',True)
        dependencies=[a['id'] for a in ledger['actions'] if a.get('active',True) and item['id'] in a.get('dependencies',[])]
        actions.append({'id':item['id'],'action':item['action'],'at':item['at'],'active':active,
                        'can_undo':active and not dependencies,'dependents':dependencies,
                        'originals':[{**{key:redact(str(original.get(key,''))) for key in ('text','value','kind','evidence')},
                                      'source_ids':list(original.get('source_ids',[]))} for original in item['originals']],
                        'title':redact(str(item['originals'][0].get('value') or item['originals'][0].get('title') or item['originals'][0].get('text','')))})
    return {'editable':selected is not None,'compatible':compatible,'actions':actions,
            'value':selected[1].get('value','') if selected else '',
            'text':selected[1].get('intent','') if selected and selected[0]=='projects' else selected[1].get('text','') if selected else ''}
