"""User-configurable retention, grounded personal records, and separate managed storage."""
import copy,json,re
from pathlib import Path

DEFAULT_SETTINGS={'domains':['work','research','learning','personal','life','health'],'detail':'balanced'}
DETAILS={'concise':{'decisions':4,'characters':300,'session_chars':16000},
         'balanced':{'decisions':8,'characters':600,'session_chars':24000},
         'detailed':{'decisions':12,'characters':1200,'session_chars':24000}}
FILES={'personal_facts':'knowledge/personal_facts.md','preferences':'knowledge/preferences.md',
       'history':'knowledge/history.md'}
VERSION=3

def validate_settings(value):
    if not isinstance(value,dict) or set(value)-{'domains','detail'}:
        raise ValueError('Settings accept only domains and detail')
    value={**copy.deepcopy(DEFAULT_SETTINGS),**value}
    domains=value['domains']
    if not isinstance(domains,list) or not 1<=len(domains)<=20 or any(
        not isinstance(d,str) or not re.fullmatch(r'[A-Za-z0-9_\-\u4e00-\u9fff ]{1,40}',d) for d in domains):
        raise ValueError('Select at least one domain; domain names cannot contain paths')
    if value['detail'] not in DETAILS:
        raise ValueError('Detail must be concise, balanced or detailed')
    value['domains']=list(dict.fromkeys(d.strip().casefold() for d in domains))
    if any(not d for d in value['domains']):
        raise ValueError('Domain names must not be empty')
    return value

def load_settings(vault):
    path=Path(vault)/'.knowledge_settings.json'
    return validate_settings(json.loads(path.read_text(encoding='utf-8'))) if path.exists() else copy.deepcopy(DEFAULT_SETTINGS)

def save_settings(vault,value):
    from knowledge import _atomic_write
    value=validate_settings(value)
    path=Path(vault).resolve()/'.knowledge_settings.json'
    if not path.resolve().is_relative_to(Path(vault).resolve()):raise ValueError('Settings path escapes vault')
    _atomic_write(path,json.dumps(value,ensure_ascii=False,indent=2).encode())
    return value

def policy_hash(settings):
    from knowledge_pipeline import digest
    return digest({'version':VERSION,'settings':validate_settings(settings)})

def limits(settings=None):
    return DETAILS[validate_settings(settings or DEFAULT_SETTINGS)['detail']]

def validate_record(raw,session):
    from knowledge_pipeline import content_identity,unique
    from harvest import redact
    if not isinstance(raw,dict):raise ValueError('Retained record must be an object')
    r=copy.deepcopy(raw)
    for field in ('key','value','text','domain'):
        if not isinstance(r.get(field),str) or not r[field].strip() or len(r[field])>2000:
            raise ValueError('Record needs non-empty '+field)
        r[field]=redact(r[field]).strip()
    if r.get('kind') not in ('user_fact','assistant_suggestion','inference'):
        raise ValueError('Record needs a supported kind: user_fact, assistant_suggestion, or inference; received '+repr(r.get('kind')))
    known={m['id']:m for m in session['messages']}
    ids=r.get('source_ids')
    if not isinstance(ids,list) or not ids or any(not isinstance(i,str) or i not in known for i in ids):
        raise ValueError('Record has untraceable sources')
    r['source_ids']=unique(ids)
    quote=r.get('evidence','')
    if not isinstance(quote,str) or not quote.strip() or len(quote)>2000:
        raise ValueError('Record needs a short exact source quotation')
    matches=[i for i in ids if quote.strip() in known[i].get('text','')]
    if not matches:raise ValueError('Record quotation is not present in its sources')
    if r['kind']=='user_fact' and (any(content_identity(known[i])!='user_statement' for i in ids) or
        not any(content_identity(known[i])=='user_statement' for i in matches)):
        r['kind']='inference'
    r['evidence']=redact(quote.strip())
    r['observed_at']=max(known[i].get('timestamp','') for i in ids)
    r['domain']=r['domain'].casefold()
    if r.get('temporal','current') not in ('current','historical'):raise ValueError('Invalid temporal classification')
    r['temporal']=r.get('temporal','current')
    return r

def normalized(value):
    return re.sub(r'[\s_\-]+','',value).casefold()

def merge_records(state,category,records,settings):
    from knowledge_pipeline import unique
    if category not in ('personal_facts','preferences','history'):raise ValueError('Unknown record category')
    selected=validate_settings(settings)['domains']
    state.setdefault(category,[]);state.setdefault('records_history',[]);state.setdefault('retention_audit',[])
    for incoming in records:
        r=copy.deepcopy(incoming)
        if r['domain'] not in selected:
            state['retention_audit'].append({'category':category,'source_ids':r['source_ids'],'reason':'outside_selected_domains'})
            continue
        if category!='history' and (r['kind']!='user_fact' or r.get('temporal')=='historical'):
            r['original_category']=category
            if r not in state['records_history']:state['records_history'].append(r)
            continue
        matches=[old for old in state[category] if normalized(old['key'])==normalized(r['key'])]
        equal=next((old for old in matches if normalized(old['value'])==normalized(r['value'])),None)
        if equal:
            equal['source_ids']=unique(equal['source_ids']+r['source_ids'])
            equal['observed_at']=max(equal['observed_at'],r['observed_at'])
            equal.setdefault('evidence_history',[])
            if r['evidence']!=equal['evidence'] and r['evidence'] not in equal['evidence_history']:
                equal['evidence_history'].append(r['evidence'])
            continue
        if category=='preferences' and matches:
            newest=max(matches+[r],key=lambda old:old['observed_at'])
            for old in matches+[r]:
                if old is not newest and old not in state['records_history']:
                    state['records_history'].append(copy.deepcopy(old))
            state[category]=[old for old in state[category] if old not in matches]+[copy.deepcopy(newest)]
        else:
            if category=='personal_facts' and matches:
                for old in matches:old['conflict']=True
                r['conflict']=True
            state[category].append(r)

def managed_content(old,title,records,marker):
    start='<!-- selfos-managed-'+marker+' -->';end='<!-- /selfos-managed-'+marker+' -->'
    outside=re.sub(re.escape(start)+r'.*?'+re.escape(end),'',old,flags=re.S).rstrip() if start in old else old.rstrip()
    if not outside:outside='# '+title
    lines=[]
    for r in records:
        lines.extend(['- ['+r.get('kind','inference')+'] '+r['text']+(' [conflict]' if r.get('conflict') else ''),
                      '  Date: '+r.get('observed_at',''), '  Source: '+', '.join(r['source_ids'])])
        if r.get('project_title'):lines.append('  Project: '+r['project_title'])
        basis={'summary_context':'Saved-summary inference; verify raw sources for scope.',
               'project_context':'Legacy project context; event time and direct evidence unavailable.',
               'session_context':'Source conversation; date is the session time.'}.get(r.get('source_scope'))
        if basis:lines.append('  Basis: '+basis)
    return (outside+'\n\n'+start+'\n'+'\n'.join(lines)+'\n'+end+'\n').encode()

def record_writes(vault,state):
    from knowledge_pipeline import safe_path
    writes={}
    for category,path in FILES.items():
        actual=safe_path(Path(vault).resolve(),path)
        records=state.get(category,[])
        if category=='history':
            from knowledge_history import history_records
            records=history_records(state)
        old=actual.read_text(encoding='utf-8') if actual.exists() else ''
        writes[path]=managed_content(old,category.replace('_',' ').title(),records,category)
    return writes
