"""app / library responsibilities."""
import copy, json, threading
from collections import OrderedDict
from pathlib import Path
from selfos.knowledge.history import history_records as _history
from selfos.sources.text import redact
from selfos.knowledge.identity import digest
from selfos.sources.conversations import extract_conversations
from selfos.sources.conversations import local_roots
from selfos.knowledge.search import search_terms, date_bound, match_fields
from selfos.sources.documents import SourceUnavailable, document_source, source_page

CATEGORIES=('projects','lessons','personal_facts','preferences','history')


_VIEWS=OrderedDict()


_VIEW_LOCK=threading.RLock()


def _view(vault):
    vault=Path(vault).resolve();path=vault/'.knowledge_pipeline.json'
    if not path.resolve().is_relative_to(vault):raise ValueError('Knowledge state escapes vault')
    stat=path.stat() if path.exists() else None
    signature=(str(path),stat.st_mtime_ns,stat.st_ctime_ns,stat.st_size,stat.st_ino) if stat else (str(path),None)
    with _VIEW_LOCK:
        if signature not in _VIEWS:
            state=_state(vault)
            _VIEWS[signature]=(_records(state),knowledge_counts(state))
            for key in list(_VIEWS):
                if key!=signature and key[0]==str(path):del _VIEWS[key]
            while len(_VIEWS)>4:_VIEWS.popitem(last=False)
        _VIEWS.move_to_end(signature)
        return _VIEWS[signature]


def _state(vault):
    vault=Path(vault).resolve();path=vault/'.knowledge_pipeline.json'
    if not path.resolve().is_relative_to(vault):raise ValueError('Knowledge state escapes vault')
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def knowledge_counts(state):
    return {'cards':len(state.get('cards',{})),'lessons':len(state.get('lessons',[])),
        'personal_facts':len(state.get('personal_facts',[])),
        'preferences':len(state.get('preferences',[])),'history':len(_history(state))}


def _sources(state,ids):
    result=[]
    for identity in dict.fromkeys(ids):
        source=state.get('sources',{}).get(identity)
        if not isinstance(source,dict):continue
        filename=source.get('original_filename') if source.get('source')=='uploaded_file' else source.get('path','')
        result.append({'id':identity,'file':redact(str(filename or '').replace('\\','/').split('/')[-1]),
            **{key:redact(str(source.get(key,''))) for key in ('source','timestamp','role','provenance','session_id')}})
    return result


def _record_identity(category, record):
    text = record.get('intent', '') if category == 'projects' else record.get('text', '')
    return digest([category, record.get('project_id'), record.get('key'), record.get('value'),
                   text, record.get('source_ids', []), record.get('domain')])


def _records(state):
    rows=[]
    metadata={}
    aliases=state.get('project_aliases',{})
    def project_identity(identity):
        return aliases.get(identity,identity) if isinstance(identity,str) and isinstance(aliases,dict) else identity
    def sources_for(ids):
        missing=[identity for identity in ids if identity not in metadata]
        for source in _sources(state,missing):metadata[source['id']]=source
        return [metadata[i] for i in dict.fromkeys(ids) if i in metadata]
    def add(category,record):
        if not isinstance(record,dict):return
        ids=record.get('source_ids',[])
        sources=sources_for(ids)
        direct_project = project_identity(record.get('project_id'))
        project_ids = [direct_project]
        project_ids.extend(project_identity(metadata.get('project_id')) for identity in ids
                           if isinstance(metadata:=state.get('sources',{}).get(identity),dict))
        contexts = []
        for project_id in dict.fromkeys(identity for identity in project_ids if isinstance(identity, str) and identity):
            token = digest(['project_context', project_id])
            card = state.get('cards', {}).get(project_id, {})
            known_title = card.get('title') or (record.get('project_title') if project_id==direct_project else None)
            title = known_title or ('Project ' + token[:8])
            contexts.append({'id': token, 'title': redact(str(title)),
                             'title_known': bool(known_title)})
        date=record.get('updated_at') or record.get('observed_at') or max((s['timestamp'] for s in sources),default='')
        if record.get('source_scope')=='project_context':date=''
        text=record.get('intent','') if category=='projects' else record.get('text','')
        title=record.get('title','') if category=='projects' else record.get('project_title') or record.get('value') or text[:80]
        row={'id':digest([category,record.get('project_id'),record.get('key'),record.get('value'),text,ids,record.get('domain')]),
            'category':category,'title':redact(str(title)),'summary':redact(str(text)),
            'date':date,'domain':record.get('domain','work' if category=='projects' else ''),
            'kind':record.get('kind','inference'),'status':record.get('status',''),
            'source_scope':record.get('source_scope','record'),
            'original_category':record.get('original_category',''),
            'support_review':'summary_model_review' if record.get('support_review')=='summary_model_review' else '',
            'conflict':bool(record.get('conflict')),'verified':bool(record.get('verified')),
            'source_count':len(sources), 'missing_source_count':len(set(ids) - {source['id'] for source in sources}),
            'project_contexts':contexts,
            'source_types':sorted({source['source'] for source in sources if source['source']})}
        details={**row,'evidence':redact(str(record.get('evidence',''))),
            'source_scope':record.get('source_scope','record'),
            'original_category':record.get('original_category',''),
            **{field:[redact(str(v)) for v in record.get(field,[])]
               for field in ('decisions','blockers','next_steps')}}
        search=' '.join([row['title'],row['summary'],row['domain'],*details['decisions'],
            *details['blockers'],*details['next_steps']]).casefold()
        rows.append((row,details,sources,search))
    for card in state.get('cards',{}).values():add('projects',card)
    for category in CATEGORIES[1:-1]:
        for record in state.get(category,[]):add(category,record)
    for record in _history(state):add('history',record)
    ordered=sorted(rows,key=lambda row:(row[0]['date'],row[0]['id']),reverse=True)
    known_contexts={}
    for row,_,_,_ in ordered:
        for context in row['project_contexts']:
            if context['title_known'] and context['id'] not in known_contexts:
                known_contexts[context['id']]=dict(context)
    for row,_,_,_ in ordered:
        for context in row['project_contexts']:
            if context['id'] in known_contexts:context.update(known_contexts[context['id']])
    return ordered


def list_knowledge(vault,category='all',query='',offset=0,limit=50, *, project='', source='', date_from='', date_to=''):
    if not isinstance(category,str) or category not in ('all',*CATEGORIES):raise ValueError('Unknown knowledge category')
    terms = search_terms(query)
    if not isinstance(project,str) or len(project)>100:raise ValueError('Invalid project filter')
    if not isinstance(source,str) or len(source)>80:raise ValueError('Invalid source filter')
    date_from,date_to = date_bound(date_from),date_bound(date_to)
    if date_from and date_to and date_from>date_to:raise ValueError('Date range is reversed')
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=200:raise ValueError('Limit must be 1..200')
    if isinstance(offset,bool) or not isinstance(offset,int) or offset<0:raise ValueError('Offset must be non-negative')
    records,counts=_view(vault)
    projects = {context['id']:context for row,_,_,_ in records for context in row['project_contexts']}
    sources = sorted({kind for row,_,_,_ in records for kind in row['source_types']})
    rows=[];filtered_counts=dict.fromkeys(CATEGORIES,0)
    for row,details,_,_ in records:
        if project and not any(context['id']==project for context in row['project_contexts']):continue
        if source and source not in row['source_types']:continue
        if date_from or date_to:
            try:observed=date_bound(row['date'][:10])
            except (ValueError,TypeError):continue
            if not observed or (date_from and observed<date_from) or (date_to and observed>date_to):continue
        fields={name:' '.join(details[name]) for name in ('decisions','blockers','next_steps')}
        fields.update(title=row['title'],summary=row['summary'],evidence=details['evidence'],
                      domain=row['domain'],project_context=' '.join(context['title'] for context in row['project_contexts'] if context['title_known']))
        match=match_fields(fields,query,terms)
        if match is None:continue
        filtered_counts[row['category']]+=1
        if category=='all' or row['category']==category:rows.append({**row,**match})
    rows.sort(key=lambda row:(row['search_score'],row['date'],row['id']),reverse=True)
    return copy.deepcopy({'items':rows[offset:offset+limit],'total':len(rows),
        'offset':offset,'limit':limit,'counts':counts,'filtered_counts':filtered_counts,
        'filters':{'projects':sorted(projects.values(),key=lambda context:(context['title'],context['id'])),
                   'sources':sources}})


def knowledge_detail(vault,identity,source_offset=0,source_limit=30):
    if not isinstance(source_offset,int) or source_offset<0 or not isinstance(source_limit,int) or not 1<=source_limit<=100:
        raise ValueError('Invalid source pagination')
    for row,details,sources,_ in _view(vault)[0]:
        if row['id']==identity:
            sources=sorted(sources,key=lambda s:s['timestamp'],reverse=True)
            return copy.deepcopy({'item':details,'sources':sources[source_offset:source_offset+source_limit],
                    'source_count':len(sources),'source_offset':source_offset})
    raise KeyError('Knowledge item not found; it may have changed after organizing')


def knowledge_source(vault,identity, *, offset=0,limit=24000):
    state=_state(vault);source=state.get('sources',{}).get(identity)
    if not isinstance(source,dict):raise KeyError('Unknown conversation source')
    if source.get('source')=='uploaded_file':
        return {**_sources(state,[identity])[0],**document_source(vault,source,offset,limit)}
    path=Path(source.get('path','')).resolve()
    if path.suffix.lower()!='.jsonl':
        raise SourceUnavailable('unsupported_source_format','Conversation source format is not supported')
    if not any(path.is_relative_to(Path(root).resolve()) for root in local_roots()):
        raise SourceUnavailable('source_denied','Conversation source is outside supported source folders')
    if not path.is_file():
        raise SourceUnavailable('source_missing','Conversation source is missing or has moved')
    for message in extract_conversations([path]):
        if message['id']==identity:
            return {**_sources(state,[identity])[0],**source_page(message['text'],offset,limit)}
    raise SourceUnavailable('source_changed','Conversation source changed; the original message could not be verified')


def knowledge_timeline(vault, identity, category="all", offset=0, limit=50, revision=''):
    from selfos.knowledge.timeline import project_timeline
    if category not in ("all", "goals", "decisions", "progress", "blockers"):
        raise ValueError("Unknown timeline category")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("Offset must be non-negative")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
        raise ValueError("Limit must be 1..200")
    if not isinstance(revision, str) or (revision and (len(revision) != 64 or any(c not in '0123456789abcdef' for c in revision))):
        raise ValueError('Invalid timeline revision')
    state = _state(vault)
    for project_id, card in state.get("cards", {}).items():
        if isinstance(card, dict) and _record_identity('projects', card) == identity:
            result = project_timeline(state, project_id)
            current_revision = digest(result)
            reset_required = bool(revision and revision != current_revision)
            if reset_required:offset = 0
            entries = [entry for entry in result["entries"] if category == "all" or entry["type"] == category]
            page = copy.deepcopy(entries[offset:offset + limit])
            for entry in page:
                entry["sources"] = _sources(state, entry["source_ids"])
                entry["unavailable_source_count"] = len(entry["source_ids"]) - len(entry["sources"])
            return {"project_id": identity, "current": result["current"], "items": page,
                    "total": len(entries), "offset": offset, "limit": limit,
                    "revision": current_revision, "reset_required": reset_required}
    raise KeyError("Project not found; it may have changed after organizing")
