import copy,json
import pytest


def fixture(count=1):
    basis=[{'text':'Use a binary decision to gate incoming memory writes; compare gating against no gating.',
            'source_ids':[f'm{i}'],'kind':'inference','domain':'work'} for i in range(count)]
    result={'project':None,'lessons':[{'text':'Memory gating requires labeled training data.',
                                     'source_ids':[f'm{i}'],'kind':'inference','domain':'work'} for i in range(count)],
            'observations':[]}
    return result,basis


def responder(change=None):
    calls=[]
    def request(req,**kwargs):
        body=json.loads(req.data);calls.append(body);prompt=json.loads(body['messages'][0]['content'])
        verdicts=[{'id':row['id'],'action':'rewrite','text':'Gate memory writes through a binary decision and isolate its effect with a gating/no-gating comparison.',
                   'evidence_ids':row['evidence_ids'],'reason':'No labeled training requirement appears in the supplied basis.'}
                  for row in prompt['methods']]
        if change:change(verdicts,prompt,len(calls))
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return json.dumps({'content':[{'type':'tool_use','name':'review_method_support','input':{'verdicts':verdicts}}]}).encode()
        return Response()
    return request,calls


def check(result,basis,request,cancel=lambda:False):
    from knowledge_method_support import review_method_support
    return review_method_support(result,basis,'test','https://example.test',open_request=request,cancel=cancel)


def test_unsupported_training_requirement_is_corrected_with_sources_and_audit():
    result,basis=fixture();original=copy.deepcopy(result);request,calls=responder()
    checked=check(result,basis,request)
    assert result==original
    assert 'training' not in checked['lessons'][0]['text']
    assert checked['lessons'][0]['source_ids']==['m0']
    assert checked['_method_support_review'][0]['before']==original['lessons'][0]['text']
    assert checked['_method_support_review'][0]['action']=='rewrite'
    assert checked['_additional_api_calls']==1
    assert len(calls)==1


def test_project_only_measurement_returns_to_context_without_losing_basis():
    result,basis=fixture();basis[0]['text']='This experiment reduced input tokens by 41%; generalization remains untested.'
    def context(values,prompt,attempt):values[0].update(action='context',text='',evidence_ids=[])
    request,_=responder(context);checked=check(result,basis,request)
    assert checked['lessons']==[]
    assert checked['observations'][0]['text']==basis[0]['text']
    assert checked['observations'][0]['source_ids']==['m0']
    assert checked['observations'][0]['kind']=='inference'


@pytest.mark.parametrize('bad',['missing','unknown_evidence','wrong_method_evidence','empty_rewrite','retain_with_new_text'])
def test_invalid_support_response_is_rejected_without_mutating_result(bad):
    from knowledge import ResponseFormatError
    result,basis=fixture(2);original=copy.deepcopy(result)
    def corrupt(values,prompt,attempt):
        if bad=='missing':values.pop()
        elif bad=='unknown_evidence':values[0]['evidence_ids']=['invented']
        elif bad=='wrong_method_evidence':values[0]['evidence_ids']=values[1]['evidence_ids']
        elif bad=='empty_rewrite':values[0]['text']=''
        else:values[0]['action']='retain'
    request,calls=responder(corrupt)
    with pytest.raises(ResponseFormatError) as captured:check(result,basis,request)
    assert len(calls)==captured.value.additional_api_calls==2
    assert result==original


def test_support_batches_are_bounded_and_stop_prevents_next_request():
    from concurrent.futures import CancelledError
    result,basis=fixture(9);request,calls=responder()
    with pytest.raises(CancelledError) as captured:check(result,basis,request,cancel=lambda:bool(calls))
    assert len(calls)==captured.value.additional_api_calls==1
    assert len(json.loads(calls[0]['messages'][0]['content'])['methods'])<=8


def test_no_methods_means_no_support_request():
    request,calls=responder()
    result={'lessons':[],'observations':[]}
    assert check(result,[],request)==result
    assert not calls


def test_missing_source_basis_is_not_silently_accepted():
    result,basis=fixture();request,calls=responder()
    with pytest.raises(ValueError,match='basis'):check(result,[],request)
    assert not calls


def test_rewrite_keeps_all_sources_from_cited_basis_and_remains_unverified():
    result,basis=fixture();basis[0]['source_ids'].append('m1')
    result['lessons'][0]['verified']=True
    request,_=responder();checked=check(result,basis,request)
    assert checked['lessons'][0]['source_ids']==['m0','m1']
    assert checked['lessons'][0]['verified'] is False
    assert checked['_method_support_review'][0]['source_ids']==['m0','m1']


def test_identical_corrected_methods_coalesce_with_complete_sources():
    result,basis=fixture(2);request,_=responder()
    checked=check(result,basis,request)
    assert len(checked['lessons'])==1
    assert checked['lessons'][0]['source_ids']==['m0','m1']
    assert len(checked['_method_support_review'])==2


def test_same_corrected_text_in_different_domains_stays_separate():
    result,basis=fixture(2)
    result['lessons'][1]['domain']=basis[1]['domain']='research'
    request,_=responder();checked=check(result,basis,request)
    assert len(checked['lessons'])==2


@pytest.mark.parametrize('method,basis_text',[
    ('The binary write gate requires labeled training data.','Gate memory writes with a binary decision; compare gating and no gating.'),
    ('Aggregate measurement across independent runs before drawing conclusions.','Single-sample conclusions are unreliable; aggregate across multiple conversation samples.'),
    ('Decouple retrieval state from model execution to isolate model randomness.','When retrieval input is invariant but model output differs, the observed difference is attributable to model randomness.'),
    ('写入门控需要标注训练数据。','通过二元判断控制记忆写入，对照启用和关闭门控。'),
    ('需要重复运行实验后汇总结果。','单个样本结论不可靠，需要汇总多个会话样本。'),
    ('将检索状态与模型执行解耦来分析随机性。','检索输入相同但模型输出不同，可分析模型随机性。')])
def test_known_unsupported_assumptions_cannot_pass_a_retain_verdict(method,basis_text):
    from knowledge import ResponseFormatError
    result,basis=fixture();result['lessons'][0]['text']=method;basis[0]['text']=basis_text
    def retain(values,prompt,attempt):values[0].update(action='retain',text='')
    request,calls=responder(retain)
    with pytest.raises(ResponseFormatError,match='unsupported') as captured:check(result,basis,request)
    assert len(calls)==captured.value.additional_api_calls==2


def test_explicitly_supported_repeated_run_design_is_not_rejected():
    result,basis=fixture()
    result['lessons'][0]['text']='Aggregate measurements across repeated runs with different seeds.'
    basis[0]['text']='Repeat the experiment with different random seeds and aggregate measurements across the runs.'
    def retain(values,prompt,attempt):values[0].update(action='retain',text='')
    request,_=responder(retain)
    assert check(result,basis,request)['lessons'][0]['text']==result['lessons'][0]['text']


def test_explicit_training_and_decoupling_basis_remains_usable():
    result,basis=fixture()
    result['lessons'][0]['text']='The classifier requires labeled training data; decouple data loading from model execution.'
    basis[0]['text']='Train the classifier on labeled training data and decouple data loading from model execution to analyze invariant inputs.'
    def retain(values,prompt,attempt):values[0].update(action='retain',text='')
    request,_=responder(retain)
    assert check(result,basis,request)['lessons']


def test_legacy_method_domain_is_explicit_after_support_rewrite():
    result,basis=fixture()
    result['lessons'][0].pop('domain')
    basis[0].pop('domain')
    original=copy.deepcopy(result)
    request,_=responder()
    checked=check(result,basis,request)
    assert checked['lessons'][0]['domain']=='work'
    assert result==original


def test_legacy_context_domain_is_explicit_after_support_routing():
    result,basis=fixture()
    basis[0].pop('domain')
    def context(values,prompt,attempt):values[0].update(action='context',text='',evidence_ids=[])
    request,_=responder(context)
    checked=check(result,basis,request)
    assert checked['observations'][0]['domain']=='work'


def test_unclassified_legacy_basis_can_support_an_explicitly_classified_method():
    result,basis=fixture()
    result['lessons'][0]['domain']='research'
    basis[0].pop('domain')
    original=copy.deepcopy(basis)
    request,_=responder()
    checked=check(result,basis,request)
    assert checked['lessons'][0]['domain']=='research'
    assert basis==original


def test_explicit_foreign_domain_basis_is_still_rejected():
    result,basis=fixture()
    basis[0]['domain']='research'
    request,calls=responder()
    with pytest.raises(ValueError,match='source-linked candidate basis'):check(result,basis,request)
    assert calls==[]
