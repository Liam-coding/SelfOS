"""Source-backed revision metadata; never trust a model-supplied clock."""
import copy
import re
from datetime import date
from selfos.knowledge.filtering import content_identity
from selfos.knowledge.identity import normalized
from selfos.knowledge.identity import unique


def validate_revision(record, known):
    revision=record.get('revision')
    # Effective dates are computed only from validated revision evidence.
    record.pop('valid_from',None)
    record.pop('valid_until',None)
    record.pop('validity_source_ids',None)
    record.pop('validity_evidence',None)
    record.pop('validity_conflict',None)
    record.pop('scheduled',None)
    record.pop('has_future_support',None)
    record.pop('manual_correction',None)
    record.pop('revisions',None)
    if revision is None:return record
    if not isinstance(revision,dict):raise ValueError('Invalid preference revision')
    revision=copy.deepcopy(revision)
    identity=revision.get('source_id')
    if not isinstance(identity,str):raise ValueError('Invalid preference revision source')
    source=known.get(identity)
    quote=revision.get('evidence')
    previous=revision.get('previous_value')
    if not source or content_identity(source)!='user_statement':
        raise ValueError('Preference revision needs direct user evidence')
    if not isinstance(quote,str) or not quote or len(quote)>2000 or quote not in source.get('text',''):
        raise ValueError('Preference revision has unsupported evidence')
    if (not isinstance(previous,str) or not previous or len(previous)>2000
        or normalized(previous) not in normalized(quote)
        or normalized(record['value']) not in normalized(quote)
        or normalized(previous)==normalized(record['value'])):
        raise ValueError('Preference revision must quote previous and new values')
    if not re.search(r'\b(changed?|switched?|instead|now|replaced?|used to)\b|改为|改成|不再|以后|现在',quote,re.I):
        raise ValueError('Preference revision needs explicit change evidence')
    if re.search(r'\b(?:hypothetical|example)\b|假设|示例',quote,re.I):
        raise ValueError('Preference revision cannot rely on a negated or hypothetical change')
    patterns=[r'\b(?:changed?|switched?|replaced?)\s+(.+?)\s+(?:to|with|for)\s+(.+)',
              r'\bprefer\s+(.+?)\s+(?:instead of|rather than)\s+(.+)',
              r'\b(?:do not want|used to prefer)\s+(.+?)(?:anymore|;|,).+?\b(?:now.+?)?prefer\s+(.+)',
              r'(?:把|从)?(.+?)(?:改为|改成)(.+)',
              r'不再(.+?)[，；;].*?现在(?:喜欢|偏好|希望|用)(.+)']
    directed=False;change_clause=''
    for index,pattern in enumerate(patterns):
        match=re.search(pattern,quote,re.I)
        if not match:continue
        before,after=match.groups()
        if index==1:before,after=after,before
        if normalized(previous) in normalized(before) and normalized(record['value']) in normalized(after):
            action=match.start()
            if index==2:
                actions=list(re.finditer(r'\bprefer\s',match.group(),re.I))
                action=match.start()+actions[-1].start()
                if not re.search(r'\bnow\s+(?:I\s+)?(?:would\s+)?$',quote[:action],re.I):continue
            prefix=re.split(r'[.;!?。；]',quote[:action])[-1]
            if index!=2 and re.search(r"\b(?:not|never|don't|doesn't|didn't|won't|wouldn't|can't|cannot|haven't|hasn't)\b|没有|并未|不会|不打算",prefix,re.I):continue
            if index>=3 and re.search(r'没有|并未|不会|不打算',before):continue
            start=max((quote.rfind(c,0,action) for c in '.;!?。；'),default=-1)+1
            stops=[quote.find(c,action) for c in '.;!?。；' if quote.find(c,action)>=0]
            end=min(stops) if stops else len(quote)
            change_clause=quote[start:end]
            directed=True;break
    if not directed:raise ValueError('Preference revision direction is not supported by its quotation')
    effective=revision.get('effective_at','')
    if not isinstance(effective,str):raise ValueError('Invalid preference revision date')
    basis=revision.get('effective_basis','')
    if effective=='source-time' or basis=='source-time':
        from selfos.knowledge.temporal import instant
        now_bound=re.search(r'\bfrom\s+now\b|\bnow\s+(?:I\s+)?(?:change|switch|replace|prefer)\b|\b(?:change|switch|replace|prefer)\b.{0,200}\bnow\s*$|现在|即日起',change_clause,re.I)
        if (re.search(r'\b(?:not|never)\s+(?:right\s+)?now\b|不是现在|并非现在',change_clause,re.I)
            or re.search(r'(?:\bfrom|\beffective(?:\s+from)?|\bstarting|从|自)\s*\d{4}-\d{2}-\d{2}',change_clause,re.I)):
            now_bound=None
        if not now_bound or instant(source.get('timestamp')) is None:
            raise ValueError('Preference revision source time is ambiguous')
        if basis=='source-time' and effective!=source['timestamp']:
            raise ValueError('Preference revision clock differs from its source')
        effective=source['timestamp'];basis='source-time'
    elif effective:
        try:valid=date.fromisoformat(effective).isoformat()==effective
        except (ValueError,TypeError):valid=False
        qualifier=r'(?:\bfrom|\beffective(?:\s+from)?|\bstarting|\bas of|从|自|生效(?:日期)?[:：]?)\s*'+re.escape(effective)
        if not valid or not re.search(qualifier,change_clause,re.I):
            raise ValueError('Preference revision date is not explicitly supported')
        basis='quoted-date'
    revision={key:revision[key] for key in ('previous_value','source_id','evidence')}
    revision.update(effective_at=effective,effective_basis=basis)
    record['revision']=revision
    record['revisions']=[copy.deepcopy(revision)]
    record['source_ids']=unique(record['source_ids']+[revision['source_id']])
    support={'source_id':revision['source_id'],'evidence':revision['evidence'],
             'observed_at':source.get('timestamp','')}
    if support not in record['supporting_observations']:record['supporting_observations'].append(support)
    if effective:
        record['valid_from']=effective
        record['validity_source_ids']=[revision['source_id']]
    return record
