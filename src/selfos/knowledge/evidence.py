"""knowledge / evidence responsibilities."""
import json
import re

RECORD_SCHEMA = {
    'required': ['key', 'value', 'text', 'domain', 'kind', 'temporal', 'evidence_id'],
    'kind': ['user_fact', 'assistant_suggestion', 'inference'],
    'temporal': ['current', 'historical'],
    'example': {'key': 'communication.language', 'value': 'Chinese',
        'text': 'Prefers Chinese explanations', 'domain': 'personal',
        'kind': 'user_fact', 'temporal': 'current', 'evidence_id': 's1:e1'},
}


def normalize_wire_arrays(result):
    """Some compatible gateways encode array-valued tool arguments a second time."""
    array_fields={'lessons','observations','verdicts','personal_facts','preferences','history','source_ids',
                  'decisions','blockers','next_steps','context_source_ids'}
    def visit(value):
        if isinstance(value,dict):
            for field,child in list(value.items()):
                if field in array_fields and isinstance(child,str):
                    try:decoded=json.loads(child)
                    except ValueError as error:raise ValueError(field+' contains malformed JSON array') from error
                    if not isinstance(decoded,list):raise ValueError(field+' must decode to an array')
                    value[field]=decoded
                    child=decoded
                visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
    visit(result)
    return result


def portable_strict_schema(value):
    """Keep the strict-decoding subset supported by the configured provider.

    Source validation and size limits are still enforced by local validators.
    """
    unsupported={'minItems','maxItems','uniqueItems','minLength','maxLength'}
    if isinstance(value,dict):
        return {k:portable_strict_schema(v) for k,v in value.items() if k not in unsupported}
    if isinstance(value,list):return [portable_strict_schema(v) for v in value]
    return value


def output_schema(aliases, references, decision_budget):
    text = {'type': 'string', 'minLength': 1, 'maxLength': 2000}
    source_ids = {'type':'array','minItems':1,'uniqueItems':True,
                  'items':{'type':'string','enum':list(aliases.values())}}
    kind = {'type':'string','enum':RECORD_SCHEMA['kind']}
    record = {'type':'object','additionalProperties':False,'required':RECORD_SCHEMA['required'],
        'properties':{**{k:text for k in ('key','value','text','domain')}, 'kind':kind,
            'temporal':{'type':'string','enum':['current','historical']},
            'evidence_id':{'type':'string','enum':list(references)}}}
    strings = lambda maximum: {'type':'array','maxItems':maximum,'items':text}
    revision={'type':'object','additionalProperties':False,
        'required':['previous_value','effective_at','evidence_id'],
        'properties':{'previous_value':text,'effective_at':{'type':'string'},
                      'evidence_id':record['properties']['evidence_id']}}
    preference = {**record, 'required':[*record['required'], 'scope','revision'],
        'properties':{**record['properties'], 'scope':{
            'type':'object', 'additionalProperties':False, 'required':['type','id'],
            'properties':{'type':{'type':'string','enum':['global','activity','project','unknown']},
                          'id':{'type':'string','maxLength':200}}},
                      'revision':{'anyOf':[revision,{'type':'null'}]}}}
    from selfos.knowledge.personal_facts import CLAIM_TYPES
    fact={**record,'required':[*record['required'],'scope','claim_type','context_source_ids'],
          'properties':{**record['properties'],'scope':preference['properties']['scope'],
                        'claim_type':{'type':'string','enum':list(CLAIM_TYPES)},
                        'context_source_ids':{'type':'array','uniqueItems':True,
                            'items':{'type':'string','enum':list(aliases.values())}}}}
    project = {'type':'object','additionalProperties':False,
        'required':['project_id','title','domain','intent','status','decisions','blockers','next_steps','source_ids','updated_at','verified'],
        'properties':{'project_id':{'type':'string','enum':['current-project']},
            **{k:text for k in ('title','domain','intent')},
            'status':{'type':'string','enum':['in_progress','blocked','paused','reported_complete','completed','unknown']},
            'decisions':strings(decision_budget),'blockers':strings(12),'next_steps':strings(12),
            'source_ids':source_ids,'updated_at':{'type':'string'},'verified':{'type':'boolean'}}}
    lesson = {'type':'object','additionalProperties':False,'required':['text','domain','kind','source_ids'],
        'properties':{'text':text,'domain':text,'kind':kind,'source_ids':source_ids}}
    return {'type':'object','additionalProperties':False,
        'required':['project','lessons','personal_facts','preferences','history'],
        'properties':{'project':{'anyOf':[project,{'type':'null'}]},
            'lessons':{'type':'array','maxItems':12,'items':lesson},
            **{k:{'type':'array','maxItems':100,'items':preference if k=='preferences' else fact if k=='personal_facts' else record}
               for k in ('personal_facts','preferences','history')}}}


def synthesis_schema(aliases,decision_budget):
    base=output_schema(aliases,{},decision_budget)['properties']
    observation={**base['lessons']['items'],'properties':{
        **base['lessons']['items']['properties'],'kind':{'type':'string','enum':['inference']}}}
    return {'type':'object','additionalProperties':False,'required':['project','lessons','observations'],
        'properties':{'project':base['project']['anyOf'][0],
                      'lessons':{'type':'array','items':base['lessons']['items']},
                      'observations':{'type':'array','items':observation}}}


def input_evidence(messages, aliases):
    conversations, references = [], {}
    for message in messages:
        alias = aliases[message['id']]
        spans = []
        narrative_ids = []
        fence = None
        for line in message['text'].splitlines():
            marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
            boundary = False
            if marker:
                run, suffix = marker.groups()
                if fence is None:
                    fence = (run[0], len(run))
                    boundary = True
                elif run[0] == fence[0] and len(run) >= fence[1] and not suffix.strip():
                    fence = None
                    boundary = True
            narrative = fence is None and not boundary
            for start in range(0, len(line), 500):
                quote = line[start:start+500].strip()
                if not quote:
                    continue
                ref = f'{alias}:e{len(spans)+1}'
                spans.append({'id': ref, 'text': quote})
                references[ref] = (message['id'], quote)
                if narrative:
                    narrative_ids.append(ref)
        conversations.append({**{k:message.get(k,'') for k in ('role','timestamp','project','provenance')},
                              'id': alias, 'evidence_spans': spans,
                              'narrative_evidence_ids': narrative_ids})
    return conversations, references


def preserve_reported_test_outcomes(result, conversations):
    """Keep explicit prose test-count reports as unverified history, not proof.

    This narrow loss guard copies evidence rather than manufacturing a conclusion.
    Hypothetical/quoted material is excluded; ambiguous reports remain model work.
    """
    history = result.setdefault('history', [])
    if not isinstance(history, list):
        return result
    project = result.get('project') or {}
    domain = project.get('domain', 'work')
    for conversation in conversations:
        if conversation.get('role') != 'assistant' or conversation.get('provenance') not in ('', 'assistant_suggestion'):
            continue
        narrative = set(conversation.get('narrative_evidence_ids', []))
        for span in conversation['evidence_spans']:
            text = span['text']
            if span['id'] not in narrative:
                continue
            if not re.search(r'\b(?:pytest|unittest|vitest|jest|tests?|test suite)\b|测试', text, re.I):
                continue
            if not re.search(r'\b[0-9]+[ 	]+(?:passed|failed|skipped)\b|[0-9]+[ 	]*(?:项|个)?(?:测试)?(?:通过|失败|跳过)', text, re.I):
                continue
            if re.search(r'\b(?:expect|expected|would|should|will|could|might|example|hypothetical|mock|if|not|never)\b|预计|预期|假设|示例|模拟|未运行|没有运行', text, re.I):
                continue
            if any((item.get('key') == 'project.reported_test_outcome' and item.get('evidence_id') == span['id'])
                   or text in item.get('text', '') for item in history if isinstance(item, dict)):
                continue
            history.append({'key':'project.reported_test_outcome','value':text,
                'text':'Unverified assistant test report: ' + text,'domain':domain,
                'kind':'inference','temporal':'historical','evidence_id':span['id']})
    return result


def resolve_evidence(result, references, originals):
    for category in ('personal_facts', 'preferences', 'history'):
        records = result.get(category, [])
        if not isinstance(records, list):
            raise ValueError(category + ' must be an array')
        for index, record in enumerate(records):
            if isinstance(record,dict) and isinstance(record.get('revision'),dict):
                revision=record['revision']
                if 'evidence_id' in revision:
                    ref=revision.pop('evidence_id')
                    if not isinstance(ref,str) or ref not in references:
                        raise ValueError('Preference revision has unknown evidence_id')
                    revision['source_id'],revision['evidence']=references[ref]
            if not isinstance(record, dict) or 'evidence_id' not in record:
                continue  # Legacy exact quotations still undergo strict validation.
            ref = record['evidence_id']
            if not isinstance(ref, str) or ref not in references:
                raise ValueError(f'{category}[{index}] has unknown evidence_id; copy one exact input evidence ID')
            identity, quote = references[ref]
            record['evidence_source_id']=identity
            declared = record.get('source_ids')
            if declared is not None and (not isinstance(declared, list) or not declared or
                any(not isinstance(i,str) for i in declared) or
                identity not in [originals.get(i,i) for i in declared]):
                raise ValueError(f'{category}[{index}] evidence does not match its declared source')
            record['source_ids'] = [identity] if declared is None else [originals.get(i,i) for i in declared]
            contextual=record.get('context_source_ids',[])
            if not isinstance(contextual,list) or any(not isinstance(i,str) or i not in originals and i not in originals.values() for i in contextual):
                raise ValueError(f'{category}[{index}] has unknown contextual sources')
            record['context_source_ids']=[originals.get(i,i) for i in contextual]
            record['source_ids']=list(dict.fromkeys(record['source_ids']+record['context_source_ids']))
            record['evidence'] = quote
    return result
