"""knowledge / records responsibilities."""
import copy, re
from selfos.knowledge.settings import validate_settings

def validate_record(raw,session):
    from selfos.knowledge.filtering import content_identity
    from selfos.knowledge.identity import unique
    from selfos.sources.text import redact
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
    from selfos.knowledge.identity import unique
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
