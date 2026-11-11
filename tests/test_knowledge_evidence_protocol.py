import selfos.providers.knowledge as _providers_knowledge
import urllib.request as _urllib_request
import copy,json
from pathlib import Path
import pytest

from selfos.knowledge.projects import validate_summary
from tests.test_project_knowledge_contract import session


def response(monkeypatch, record, category='preferences'):
    captured=[]
    result={'project':None,'lessons':[],category:[record]}
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return json.dumps({'content':[{'type':'text','text':json.dumps(result)}]}).encode()
    def request(req,**kwargs):captured.append(json.loads(req.data));return Response()
    monkeypatch.setattr(_providers_knowledge,'_get_api_config',lambda _:('test-key','https://example.test'))
    monkeypatch.setattr(_urllib_request,'urlopen',request)
    monkeypatch.setattr(__import__('selfos.providers.client', fromlist=['*']), 'request_opener', lambda root: _urllib_request.urlopen)
    return _providers_knowledge.api_summarizer(Path('.'),review_records=False),captured


def record(**changes):
    return {'key':'communication.language','value':'Chinese','text':'Prefers Chinese',
        'domain':'personal','kind':'user_fact','temporal':'current','evidence_id':'s1:e1',**changes}


def test_evidence_reference_resolves_exact_quote_and_source(monkeypatch):
    item=session('I prefer Chinese explanations.')
    summarize,captured=response(monkeypatch,record())
    result=summarize(item)
    value=validate_summary(result,item)['preferences'][0]
    assert value['source_ids']==['m1'] and value['evidence']==item['messages'][0]['text']
    prompt=json.loads(captured[0]['messages'][0]['content'])
    assert prompt['conversations'][0]['evidence_spans'][0]=={'id':'s1:e1','text':item['messages'][0]['text']}
    assert prompt['record_schema']['kind']==['user_fact','assistant_suggestion','inference']


def test_unknown_evidence_id_is_rejected_with_raw_diagnostic(monkeypatch):
    summarize,_=response(monkeypatch,record(evidence_id='s99:e1'))
    with pytest.raises(ValueError,match='evidence') as failure:summarize(session('I prefer Chinese explanations.'))
    assert 's99:e1' in failure.value.raw_response


def test_evidence_reference_cannot_point_to_a_different_declared_source(monkeypatch):
    summarize,_=response(monkeypatch,record(source_ids=['s2']))
    item=session('I prefer Chinese explanations.')
    item['messages'].append({**item['messages'][0],'id':'m2','text':'Other conversation'})
    with pytest.raises(ValueError,match='source'):summarize(item)


def test_assistant_evidence_does_not_become_a_user_fact(monkeypatch):
    summarize,_=response(monkeypatch,record())
    item=session('I suggest Chinese explanations.',role='assistant')
    validated=validate_summary(summarize(item),item)
    assert validated['preferences'][0]['kind']=='inference'


def test_legacy_exact_quotes_still_validate_and_paraphrases_do_not(monkeypatch):
    raw=record(source_ids=['s1'],evidence='I prefer Chinese explanations.')
    raw.pop('evidence_id')
    summarize,_=response(monkeypatch,raw)
    item=session('I prefer Chinese explanations.')
    assert validate_summary(summarize(item),item)['preferences']
    raw['evidence']='The user likes Chinese.'
    summarize,_=response(monkeypatch,raw)
    with pytest.raises(ValueError,match='quotation'):validate_summary(summarize(item),item)


def test_evidence_spans_preserve_all_input_characters(monkeypatch):
    item=session('a'*510+'\nI prefer Chinese explanations.')
    summarize,captured=response(monkeypatch,record(evidence_id='s1:e3'))
    result=summarize(item)
    assert validate_summary(result,item)['preferences'][0]['evidence']=='I prefer Chinese explanations.'
    prompt=json.loads(captured[0]['messages'][0]['content'])
    spans=prompt['conversations'][0]['evidence_spans']
    assert all(span['text'] in item['messages'][0]['text'] for span in spans)


def test_api_requests_schema_constrained_local_extraction_tool(monkeypatch):
    summarize,captured=response(monkeypatch,record())
    summarize(session('I prefer Chinese explanations.'))
    body=captured[0]
    assert body['tool_choice']=={'type':'tool','name':'retain_knowledge','disable_parallel_tool_use':True}
    schema=body['tools'][0]['input_schema']
    assert body['tools'][0]['strict'] is True
    assert 'maxItems' not in json.dumps(schema)
    fields=schema['properties']['preferences']['items']['properties']
    assert fields['kind']['enum']==['user_fact','assistant_suggestion','inference']
    assert fields['evidence_id']['enum']==['s1:e1']
    assert 'kind' in schema['properties']['preferences']['items']['required']


def test_tool_use_input_is_parsed_and_validated_without_text_json(monkeypatch):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return json.dumps({'content':[{'type':'tool_use','name':'retain_knowledge',
            'input':{'project':None,'lessons':[],'preferences':[record()]}}]}).encode()
    monkeypatch.setattr(_providers_knowledge,'_get_api_config',lambda _:('test-key','https://example.test'))
    monkeypatch.setattr(_urllib_request,'urlopen',lambda *args,**kwargs:Response())
    monkeypatch.setattr(__import__('selfos.providers.client', fromlist=['*']), 'request_opener', lambda root: _urllib_request.urlopen)
    item=session('I prefer Chinese explanations.')
    assert validate_summary(_providers_knowledge.api_summarizer(None,review_records=False)(item),item)['preferences'][0]['evidence'] == item['messages'][0]['text']


def test_automatic_skill_context_is_filtered_before_extraction():
    from selfos.knowledge.filtering import compact_message
    item=session('Base directory for this skill: C:/temporary/bundled-skills/example\n# Skill instructions')
    assert compact_message(item['messages'][0]) is None


def test_json_encoded_record_arrays_are_decoded_without_weakening_validation(monkeypatch):
    item=session('I prefer Chinese explanations.')
    data={'project':None,'lessons':'[]','preferences':json.dumps([record()]),
          'personal_facts':'[]','history':'[]'}
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return json.dumps({'content':[{'type':'tool_use','name':'retain_knowledge','input':data}]}).encode()
    monkeypatch.setattr(_providers_knowledge,'_get_api_config',lambda _:('test-key','https://example.test'))
    monkeypatch.setattr(_urllib_request,'urlopen',lambda *args,**kwargs:Response())
    monkeypatch.setattr(__import__('selfos.providers.client', fromlist=['*']), 'request_opener', lambda root: _urllib_request.urlopen)
    result=_providers_knowledge.api_summarizer(None,review_records=False)(item)
    assert validate_summary(result,item)['preferences'][0]['source_ids']==['m1']
    data['preferences']=json.dumps([record(evidence_id='s99:e1')])
    with pytest.raises(ValueError,match='evidence'):_providers_knowledge.api_summarizer(None,review_records=False)(item)


def test_malformed_encoded_arrays_are_not_repaired_or_discarded(monkeypatch):
    data={'project':None,'lessons':'[broken]','preferences':[]}
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return json.dumps({'content':[{'type':'tool_use','name':'retain_knowledge','input':data}]}).encode()
    monkeypatch.setattr(_providers_knowledge,'_get_api_config',lambda _:('test-key','https://example.test'))
    monkeypatch.setattr(_urllib_request,'urlopen',lambda *args,**kwargs:Response())
    monkeypatch.setattr(__import__('selfos.providers.client', fromlist=['*']), 'request_opener', lambda root: _urllib_request.urlopen)
    with pytest.raises(ValueError,match='lessons'):_providers_knowledge.api_summarizer(None,review_records=False)(session())


def test_actual_api_loss_guard_keeps_reported_test_result_as_sourced_inference(monkeypatch):
    item=session('pytest tests/test_upload.py completed with exit code 0: 37 passed.',role='assistant')
    summarize,_=response(monkeypatch,record(),category='history')
    result=validate_summary(summarize(item),item)
    reports=[value for value in result['history'] if value['key']=='project.reported_test_outcome']
    assert len(reports)==1 and '37 passed' in reports[0]['text']
    assert reports[0]['kind']=='inference' and not reports[0].get('verified',False)
    assert reports[0]['source_ids']==['m1']
