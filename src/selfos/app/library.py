"""app / library responsibilities."""
import copy, json, threading
from collections import OrderedDict
from pathlib import Path
from selfos.knowledge.history import history_records as _history
from selfos.sources.text import redact
from selfos.knowledge.identity import digest
from selfos.sources.conversations import extract_conversations
from selfos.sources.conversations import local_roots

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
        result.append({'id':identity,'file':Path(source.get('path','')).name,
            **{key:redact(str(source.get(key,''))) for key in ('source','timestamp','role','provenance','session_id')}})
    return result


def _records(state):
    rows=[]
    metadata={}
    def sources_for(ids):
        missing=[identity for identity in ids if identity not in metadata]
        for source in _sources(state,missing):metadata[source['id']]=source
        return [metadata[i] for i in dict.fromkeys(ids) if i in metadata]
    def add(category,record):
        if not isinstance(record,dict):return
        ids=record.get('source_ids',[])
        sources=sources_for(ids)
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
            'source_count':len(sources)}
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
    return sorted(rows,key=lambda row:row[0]['date'],reverse=True)


def list_knowledge(vault,category='all',query='',offset=0,limit=50):
    if not isinstance(category,str) or category not in ('all',*CATEGORIES):raise ValueError('Unknown knowledge category')
    if not isinstance(query,str) or len(query)>500:raise ValueError('Search query is too long')
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=200:raise ValueError('Limit must be 1..200')
    if isinstance(offset,bool) or not isinstance(offset,int) or offset<0:raise ValueError('Offset must be non-negative')
    records,counts=_view(vault);query=query.strip().casefold()
    rows=[row for row in records if (category=='all' or row[0]['category']==category) and (not query or query in row[3])]
    return copy.deepcopy({'items':[r[0] for r in rows[offset:offset+limit]],'total':len(rows),
        'offset':offset,'limit':limit,'counts':counts})


def knowledge_detail(vault,identity,source_offset=0,source_limit=30):
    if not isinstance(source_offset,int) or source_offset<0 or not isinstance(source_limit,int) or not 1<=source_limit<=100:
        raise ValueError('Invalid source pagination')
    for row,details,sources,_ in _view(vault)[0]:
        if row['id']==identity:
            sources=sorted(sources,key=lambda s:s['timestamp'],reverse=True)
            return copy.deepcopy({'item':details,'sources':sources[source_offset:source_offset+source_limit],
                    'source_count':len(sources),'source_offset':source_offset})
    raise KeyError('Knowledge item not found; it may have changed after organizing')


def knowledge_source(vault,identity):
    state=_state(vault);source=state.get('sources',{}).get(identity)
    if not isinstance(source,dict):raise KeyError('Unknown conversation source')
    path=Path(source.get('path','')).resolve()
    if path.suffix.lower()!='.jsonl' or not path.is_file() or not any(path.is_relative_to(Path(root).resolve()) for root in local_roots()):
        raise ValueError('Conversation source unavailable or outside supported source folders')
    for message in extract_conversations([path]):
        if message['id']==identity:
            return {**_sources(state,[identity])[0],'text':message['text']}
    raise ValueError('Conversation source changed; the original message could not be verified')
