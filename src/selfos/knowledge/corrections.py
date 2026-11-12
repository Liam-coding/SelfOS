"""Pure durable user-action replay, separate from generated source evidence."""
import copy
from datetime import datetime, timezone
import uuid

from selfos.knowledge.identity import digest, normalized, unique
from selfos.knowledge.preferences import normalize_scope
from selfos.sources.text import redact


def record_version(category, record):
    record=copy.deepcopy(record)
    scoped=category in ('preferences','personal_facts') or record.get('original_category') in ('preferences','personal_facts')
    if scoped:normalize_scope(record)
    fields=[category,record.get('project_id'),record.get('key'),record.get('value'),
            record.get('intent','') if category=='projects' else record.get('text',''),
            record.get('source_ids',[]),record.get('domain')]
    if scoped:fields.extend([record.get('scope_type','unknown'),record.get('scope','unknown')])
    return digest(fields)


def _entries(state):
    for record in state.get('cards',{}).values():yield 'projects',record
    for category in ('personal_facts','preferences','lessons','history','records_history'):
        for record in state.get(category,[]):yield 'history' if category=='records_history' else category,record


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
    for field in ('personal_facts','preferences','lessons','history','records_history'):
        state[field]=[r for r in state.get(field,[]) if r is not record]
    for key,value in list(state.get('cards',{}).items()):
        if value is record:del state['cards'][key]


def _insert(state,category,record):
    if category=='projects':state.setdefault('cards',{})[record['project_id']]=record
    else:state.setdefault(category,[]).append(record)


def _manual(action):
    originals=action['originals']
    record=copy.deepcopy(originals[0])
    for field in ('scheduled','has_future_support','revision','revisions','valid_from','valid_until'):
        record.pop(field,None)
    record.update(action.get('patch',{}))
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


def apply_corrections(state, ledger):
    from selfos.knowledge.preferences import preference_snapshot
    result=copy.deepcopy(preference_snapshot(state))
    result.setdefault('correction_review',[])
    for action in ledger.get('actions',[]):
        if not action.get('active',True):continue
        category=action['category'];anchors=set(action['anchors']);candidates=[]
        for kind,record in list(_entries(result)):
            if kind!=category:continue
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
                    _insert(result,category,candidate);candidates.append(candidate)
            elif action['action']!='delete' and _relation(kind,record)==action['relation']:
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
