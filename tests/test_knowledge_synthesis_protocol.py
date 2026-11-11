import selfos.providers.reviews.lessons as _providers_reviews_lessons
import selfos.providers.reviews.support as _providers_reviews_support
import selfos.providers.reviews.observations as _providers_reviews_observations
import copy,json
import pytest
import knowledge
from tests.test_project_knowledge_contract import card,message


def payload():
    return {'project':card(domain='work'),'lessons':[], 'sources':{'m1':message('Use atomic writes')}}


def mock_response(monkeypatch,content):
    captured=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return json.dumps({'content':content}).encode()
    def request(req,**kwargs):captured.append(json.loads(req.data));return Response()
    monkeypatch.setattr(knowledge,'_get_api_config',lambda _:('test-key','https://example.test'))
    monkeypatch.setattr(knowledge,'urlopen',request)
    monkeypatch.setattr(__import__('selfos.providers.client', fromlist=['*']), 'request_opener', lambda root: knowledge.urlopen)
    return captured


def result():
    return {'project':card(project_id='current-project',source_ids=['s1'],domain='work'),'lessons':[],'observations':[]}


def test_synthesis_uses_strict_tool_and_maps_sources(monkeypatch):
    captured=mock_response(monkeypatch,[{'type':'tool_use','name':'synthesize_knowledge','input':result()}])
    output=knowledge.api_refiner(None)(payload())
    assert output['project']['source_ids']==['m1']
    assert output['project']['project_id']=='C:/projects/alpha'
    body=captured[0]
    assert body['tool_choice']=={'type':'tool','name':'synthesize_knowledge','disable_parallel_tool_use':True}
    schema=body['tools'][0]['input_schema']
    assert body['tools'][0]['strict'] is True
    assert schema['required']==['project','lessons','observations']
    assert 'maxItems' not in json.dumps(schema)


def test_multiple_synthesis_calls_are_rejected_with_diagnostic(monkeypatch):
    mock_response(monkeypatch,[{'type':'tool_use','name':'synthesize_knowledge','input':result()}]*2)
    with pytest.raises(knowledge.ResponseFormatError,match='ambiguous'):
        knowledge.api_refiner(None)(payload())


def test_legacy_synthesis_text_remains_parseable(monkeypatch):
    mock_response(monkeypatch,[{'type':'text','text':json.dumps(result())}])
    assert knowledge.api_refiner(None)(payload())['project']['source_ids']==['m1']


def test_synthesis_observation_source_alias_is_resolved(monkeypatch):
    data=result();data['observations']=[{'text':'Local setup uses a proxy','domain':'work','kind':'inference','source_ids':['s1']}]
    mock_response(monkeypatch,[{'type':'tool_use','name':'synthesize_knowledge','input':data}])
    assert knowledge.api_refiner(None,review_records=False)(payload())['observations'][0]['source_ids']==['m1']


def test_empty_freeform_synthesis_cannot_silently_skip_original_candidates(monkeypatch):
    calls=[]
    class Response:
        def __init__(self,content):self.content=content
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return json.dumps({'content':self.content}).encode()
    def request(req,**kwargs):
        body=json.loads(req.data);calls.append(body);name=body['tool_choice']['name']
        if name=='synthesize_knowledge':return Response([{'type':'tool_use','name':name,'input':result()}])
        if name=='review_method_support':
            methods=json.loads(body['messages'][0]['content'])['methods']
            return Response([{'type':'tool_use','name':name,'input':{'verdicts':[{'id':m['id'],'action':'retain',
                'text':'','evidence_ids':m['evidence_ids'],'reason':'Supported by candidate basis.'} for m in methods]}}])
        candidates=json.loads(body['messages'][0]['content'])['candidates']
        return Response([{'type':'tool_use','name':name,'input':{'verdicts':[{'id':c['id'],'action':'lesson',
            'lesson_group':c['id'],'lesson_text':c['text'],'observation_text':'','reason':'Supported mechanism.'} for c in candidates]}}])
    monkeypatch.setattr(knowledge,'_get_api_config',lambda _:('test-key','https://example.test'))
    monkeypatch.setattr(knowledge,'urlopen',request)
    monkeypatch.setattr(__import__('selfos.providers.client', fromlist=['*']), 'request_opener', lambda root: knowledge.urlopen)
    item=payload();item['lessons']=[{'text':'Use atomic checkpoint writes','domain':'work','kind':'inference','source_ids':['m1']}]
    output=knowledge.api_refiner(None)(item)
    assert len(calls)==3 and output['lessons'][0]['source_ids']==['m1']
    assert len(output['_lesson_review'])==1


def test_refiner_support_gate_uses_original_basis_and_corrects_expanded_claim(monkeypatch):

    mock_response(monkeypatch,[{'type':'tool_use','name':'synthesize_knowledge','input':result()}])
    def route(value,*args,**kwargs):
        value=copy.deepcopy(value)
        value['lessons'][0]['text']='Atomic writes guarantee every test passes.'
        value['_additional_api_calls']=1
        return value
    checked=[]
    def support(value,basis,*args,**kwargs):
        checked.append(copy.deepcopy(basis))
        value['lessons'][0]['text']='Use atomic writes to preserve checkpoint integrity.'
        value['_additional_api_calls']+=1
        value['_method_support_review']=[{'action':'rewrite','source_ids':['m1']}]
        return value
    monkeypatch.setattr(_providers_reviews_lessons,'review_reusable_records',route)
    monkeypatch.setattr(_providers_reviews_support,'review_method_support',support)
    item=payload();item['lessons']=[{'text':'Use atomic writes to preserve checkpoints','domain':'work','kind':'inference','source_ids':['m1']}]
    output=knowledge.api_refiner(None)(item)
    assert checked[0][0]['text']==item['lessons'][0]['text']
    assert 'every test' not in output['lessons'][0]['text']
    assert output['_additional_api_calls']==2
    assert output['_method_support_review']


def test_synthesized_method_cannot_be_its_own_support_basis(monkeypatch):

    data=result();data['lessons']=[{'text':'Unseen training dataset guarantees success','domain':'work','kind':'inference','source_ids':['s1']}]
    mock_response(monkeypatch,[{'type':'tool_use','name':'synthesize_knowledge','input':data}])
    monkeypatch.setattr(_providers_reviews_lessons,'review_reusable_records',lambda value,*args,**kwargs:value)
    checked=[]
    def support(value,basis,*args,**kwargs):checked.extend(basis);return value
    monkeypatch.setattr(_providers_reviews_support,'review_method_support',support)
    knowledge.api_refiner(None)(payload())
    assert checked and all('Unseen training' not in row['text'] for row in checked)
    assert any('Reliable local import' in row['text'] for row in checked)


def test_refiner_consolidates_project_observations_and_counts_extra_call(monkeypatch):

    data=result();data['observations']=[{'text':'Immutable sources','domain':'work','kind':'inference','source_ids':['s1']}]
    mock_response(monkeypatch,[{'type':'tool_use','name':'synthesize_knowledge','input':data}])
    def route(value,*args,**kwargs):
        value=copy.deepcopy(value);value['observations'].append({**value['observations'][0],'text':'Sources stay unchanged'})
        value['_additional_api_calls']=1
        return value
    seen=[]
    def merge(records,*args,**kwargs):
        seen.extend(records)
        return {'observations':records[:1],'calls':1,'audit':[{'source_ids':['m1']}],'errors':[]}
    monkeypatch.setattr(_providers_reviews_lessons,'review_reusable_records',route)
    monkeypatch.setattr(_providers_reviews_observations,'merge_project_observations',merge)
    output=knowledge.api_refiner(None)(payload())
    assert len(seen)==2 and len(output['observations'])==1
    assert output['_additional_api_calls']==2 and output['_observation_merges']
