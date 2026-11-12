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
    context=r.get('context_source_ids',[])
    if not isinstance(context,list) or any(not isinstance(i,str) or i not in ids for i in context):
        raise ValueError('Record has untraceable context sources')
    from selfos.knowledge.personal_facts import CLAIM_TYPES
    if 'claim_type' in r and r['claim_type'] not in CLAIM_TYPES:
        raise ValueError('Unsupported personal fact claim type')
    quote=r.get('evidence','')
    if not isinstance(quote,str) or not quote.strip() or len(quote)>2000:
        raise ValueError('Record needs a short exact source quotation')
    matches=[i for i in ids if quote.strip() in known[i].get('text','')]
    if not matches:raise ValueError('Record quotation is not present in its sources')
    if 'evidence_source_id' in r:
        if r['evidence_source_id'] not in matches:raise ValueError('Selected evidence source does not support quotation')
        matches=[r['evidence_source_id']]
    matches=[i for i in matches if i not in context]
    if not matches:raise ValueError('Record needs supporting evidence outside context references')
    direct=[i for i in matches if content_identity(known[i])=='user_statement']
    if r['kind']=='user_fact' and not direct:
        r['kind']='inference'
    supporting=direct if r['kind']=='user_fact' else matches
    r['supporting_source_ids']=unique(supporting)
    r['context_source_ids']=[i for i in r['source_ids'] if i not in supporting]
    r['evidence']=redact(quote.strip())
    from selfos.knowledge.preferences import instant
    r['supporting_observations'] = [{'source_id': identity, 'evidence': r['evidence'],
        'observed_at': known[identity].get('timestamp', '')} for identity in supporting]
    dated = [(instant(item['observed_at']), item['observed_at']) for item in r['supporting_observations']]
    precise = [(date, text) for date, text in dated if date is not None]
    r['observed_at'] = max(precise, key=lambda item: item[0])[1] if precise else r['supporting_observations'][0]['observed_at']
    r['domain']=r['domain'].casefold()
    if r.get('temporal','current') not in ('current','historical'):raise ValueError('Invalid temporal classification')
    r['temporal']=r.get('temporal','current')
    from selfos.knowledge.preferences import normalize_scope
    normalize_scope(r, session)
    from selfos.knowledge.revisions import validate_revision
    validate_revision(r,known)
    return r


from selfos.knowledge.identity import normalized


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
        if category=='personal_facts':
            from selfos.knowledge.personal_facts import retention_reason
            reason=retention_reason(r)
            if reason:
                state['retention_audit'].append({'category':category,'source_ids':r['source_ids'],'reason':reason})
                if reason not in ('temporary_request','project_choice'):
                    r.update(original_category=category,retention_reason=reason,temporal='historical')
                    if r not in state['records_history']:state['records_history'].append(r)
                continue
        if category == 'preferences':
            from selfos.knowledge.preferences import merge_preferences
            merge_preferences(state, r)
            continue
        from selfos.knowledge.preferences import normalize_scope, relation
        matches=[old for old in state[category] if normalized(old['key'])==normalized(r['key'])
                 and (category!='personal_facts' or relation(normalize_scope(old))==relation(normalize_scope(r)))]
        equal=next((old for old in matches if normalized(old['value'])==normalized(r['value'])),None)
        if equal:
            if category=='personal_facts':
                from selfos.knowledge.personal_facts import merge_fact_support, mark_conflicts
                merge_fact_support(equal,r)
                mark_conflicts(matches)
                continue
            equal['source_ids']=unique(equal['source_ids']+r['source_ids'])
            equal['observed_at']=max(equal['observed_at'],r['observed_at'])
            equal.setdefault('evidence_history',[])
            if r['evidence']!=equal['evidence'] and r['evidence'] not in equal['evidence_history']:
                equal['evidence_history'].append(r['evidence'])
            continue
        if category=='personal_facts' and matches:
            from selfos.knowledge.personal_facts import mark_conflicts
            mark_conflicts(matches+[r])
        state[category].append(r)
