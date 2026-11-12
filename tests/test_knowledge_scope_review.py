import selfos.providers.knowledge as _providers_knowledge
import urllib.request as _urllib_request
import json
import pytest

from tests.test_project_knowledge_contract import session
from tests.test_knowledge_evidence_protocol import record


def responses(monkeypatch, verdicts):
    calls=[]
    class Response:
        def __init__(self,data):self.data=data
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return json.dumps(self.data).encode()
    def request(req,**kwargs):
        calls.append(json.loads(req.data))
        if len(calls)==1:
            return Response({'content':[{'type':'tool_use','name':'retain_knowledge',
                'input':{'project':None,'lessons':[],'personal_facts':[],
                    'preferences':[record(text='Open a new branch')],'history':[]}}]})
        return Response({'content':[{'type':'tool_use','name':'review_retention',
            'input':{'verdicts':verdicts}}]})
    monkeypatch.setattr(_providers_knowledge,'_get_api_config',lambda _:('test-key','https://example.test'))
    monkeypatch.setattr(_urllib_request,'urlopen',request)
    monkeypatch.setattr(__import__('selfos.providers.client', fromlist=['*']), 'request_opener', lambda root: _urllib_request.urlopen)
    return calls


def test_transient_request_is_discarded_without_losing_project_output(monkeypatch):
    calls=responses(monkeypatch,[{'id':'preferences:0','action':'discard','reason':'one-time task request'}])
    result=_providers_knowledge.api_summarizer(None,review_records=True)(session('Open a new branch for this change.'))
    assert result['preferences']==[] and result['_additional_api_calls']==1
    assert result['_retention_review'][0]['action']=='discard'
    assert calls[1]['tool_choice']['disable_parallel_tool_use']


def test_project_specific_information_moves_to_sourced_history(monkeypatch):
    responses(monkeypatch,[{'id':'preferences:0','action':'project_history','reason':'project decision'}])
    result=_providers_knowledge.api_summarizer(None,review_records=True)(session('Use annotations in this project.'))
    assert result['preferences']==[] and result['history'][0]['source_ids']==['m1']
    assert result['history'][0]['original_category']=='preferences'


@pytest.mark.parametrize('verdicts', [[],[{'id':'unknown','action':'retain','reason':'yes'}],
    [{'id':'preferences:0','action':'retain','reason':'yes'}]*2])
def test_incomplete_unknown_or_duplicate_review_is_rejected(monkeypatch,verdicts):
    responses(monkeypatch,verdicts)
    with pytest.raises(ValueError,match='review'):_providers_knowledge.api_summarizer(None,review_records=True)(session('Open a branch.'))
