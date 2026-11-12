"""Conservative category boundaries, not a general semantic entailment judge."""
import re

CLAIM_TYPES=('stable_fact','scoped_role','preference','project_choice','observation','temporary_request','unknown')


def retention_reason(record):
    """Known incompatible categories cannot become current personal attributes.

    Legacy records have no typed claim. Narrow prose guards catch known category
    mistakes; unfamiliar phrasing stays model work rather than a personal whitelist.
    """
    claim=record.get('claim_type')
    if claim is not None and claim not in CLAIM_TYPES:
        raise ValueError('Unsupported personal fact claim type')
    if claim in ('preference','project_choice','observation','temporary_request','unknown'):
        return {'preference':'preference_claim','project_choice':'project_choice',
                'observation':'dated_observation','temporary_request':'temporary_request',
                'unknown':'uncertain_personal_claim'}[claim]
    quote=record.get('evidence','').strip()
    clauses=re.split(r'[;。；]|(?<=[.!?])\s+|,\s*(?:but|and)\s+(?=I\b)',quote,flags=re.I)
    relevant=[clause for clause in clauses if record.get('value','').casefold() in clause.casefold()]
    if relevant:quote='; '.join(relevant)
    if re.search(r'\b(?:fictional profile|AI wrote|AI generated|hypothetical|if I were)\b|虚构(?:画像|资料)|假如我是|假设我是|AI.*(?:生成|写)',quote,re.I):
        return 'nonliteral_personal_claim'
    clauses=re.split(r'[;。；]|(?<=[.!?])\s+',quote)
    relevant=[clause for clause in clauses if record.get('value','').casefold() in clause.casefold()]
    if relevant and all(re.search(r"\bI\s+(?:am not|do not|don't|never)\b|我(?:不是|并非|没有|从不)",clause,re.I) for clause in relevant):
        return 'negated_personal_claim'
    if re.search(r'\bI\s+(?:prefer|would prefer)\b|我(?:更)?(?:喜欢|偏好|倾向于)',quote,re.I):
        return 'preference_claim'
    if re.search(r'\b(?:for|in) this project\b.*\b(?:use|choose|set|build)\b|(?:这个|本)项目.*(?:使用|采用|选择)',quote,re.I):
        return 'project_choice'
    if re.match(r'(?:please\s+)?(?:retry|fix|run|open|create|debug|install|deploy)\b|^(?:请)?(?:重试|修复|运行|打开|创建|安装|部署)',quote,re.I):
        return 'temporary_request'
    if (re.search(r'\b(?:temperature|blood pressure|heart rate|weight|glucose)\b|体温|血压|心率|体重|血糖',quote,re.I)
        and re.search(r'\b(?:today|yesterday|this morning|last night|measured|was)\b|今天|昨天|今早|昨晚|测量',quote,re.I)
        and re.search(r'\d',quote)):
        return 'dated_observation'
    # Source-native value wording is a necessary lexical anchor, not proof of
    # entailment. Relations/text may be abstracted; unsupported translations or
    # synonym-only values stay reviewable history rather than invented attributes.
    value=record.get('value','').casefold()
    anchors=re.findall(r'[a-z0-9]{2,}',value)
    anchors=[a for a in anchors if a not in {'the','and','with','of','in','at','to','as','my','is','am'}]
    if not anchors:anchors=[value]
    if not any(anchor in quote.casefold() for anchor in anchors):
        return 'unsupported_value_anchor'
    return ''


def merge_fact_support(old, incoming):
    from selfos.knowledge.identity import unique
    from selfos.knowledge.temporal import instant
    old.setdefault('legacy_observed_at',[])
    for record in (old,incoming):
        if not record.get('supporting_observations') and record.get('observed_at'):
            old['legacy_observed_at']=unique(old['legacy_observed_at']+[record['observed_at']])
        old['legacy_observed_at']=unique(old['legacy_observed_at']+record.get('legacy_observed_at',[]))
    for field in ('source_ids','supporting_source_ids','context_source_ids'):
        old[field]=unique(old.get(field,[])+incoming.get(field,[]))
    old.setdefault('supporting_observations',[])
    for item in incoming.get('supporting_observations',[]):
        if item not in old['supporting_observations']:old['supporting_observations'].append(item)
    dates=[item.get('observed_at','') for item in old.get('supporting_observations',[])]+old['legacy_observed_at']
    precise=[date for date in dates if instant(date) is not None]
    if precise:old['observed_at']=max(precise,key=instant)
    old.setdefault('evidence_history',[])
    for quote in [incoming.get('evidence',''),*incoming.get('evidence_history',[])]:
        if quote and quote!=old.get('evidence') and quote not in old['evidence_history']:
            old['evidence_history'].append(quote)


def mark_conflicts(records):
    from selfos.knowledge.identity import unique, normalized
    if len({normalized(r['value']) for r in records})<2:return
    sources=unique([source for r in records for source in r.get('supporting_source_ids',r.get('source_ids',[]))])
    for record in records:record.update(conflict=True,conflict_source_ids=sources)


def reconsolidate_facts(state):
    """Alias migration changes identity, not retention or certainty of old data."""
    from selfos.knowledge.preferences import normalize_scope, relation
    from selfos.knowledge.identity import normalized
    result=[]
    for record in state.get('personal_facts',[]):
        normalize_scope(record)
        matches=[old for old in result if relation(normalize_scope(old))==relation(record)]
        equal=next((old for old in matches if normalized(old['value'])==normalized(record['value'])),None)
        if equal:merge_fact_support(equal,record)
        else:result.append(record)
        mark_conflicts(matches if equal else matches+[record])
    state['personal_facts']=result
