import copy,json
import pytest


def source(count=21):
    return [{'text':f'Method {i}: preserve the distinct supported scope.', 'source_ids':[f'm{i}'],
             'domain':'work','kind':'inference'} for i in range(count)]


def responder(change=None):
    calls=[]
    def request(req,**kwargs):
        body=json.loads(req.data);calls.append(body)
        items=json.loads(body['messages'][0]['content'])['methods']
        mappings=[{'id':row['id'],'leader':row['id'],'reason':'Distinct mechanism or scope.'} for row in items]
        if change:change(mappings,items,len(calls))
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return json.dumps({'content':[{'type':'tool_use','name':'group_methods','input':{'groups':mappings}}]}).encode()
        return Response()
    return request,calls


def merge(records,request,cancel=lambda:False):
    from selfos.providers.reviews.methods import merge_reviewed_methods
    return merge_reviewed_methods(records,'test','https://example.test',open_request=request,cancel=cancel)


def test_cross_batch_equivalent_methods_union_sources_without_rewriting_or_quota():
    records=source();original=copy.deepcopy(records)
    def same(values,items,attempt):
        values[-1]['leader']=values[0]['id']
    request,calls=responder(same)
    result=merge(records,request)
    assert records==original and len(result['lessons'])==20
    assert result['lessons'][0]['text']==records[0]['text']
    assert result['lessons'][0]['source_ids']==['m0','m20']
    assert len(calls)==result['calls']==1
    assert len(result['audit'])==21


def test_distinct_methods_all_survive():
    records=source(81);request,calls=responder()
    result=merge(records,request)
    assert result['lessons']==records
    assert len(calls)==3
    windows=[{r['id'] for r in json.loads(body['messages'][0]['content'])['methods']} for body in calls]
    assert all(len(window)<=80 for window in windows)
    assert all(any({f'l{i}',f'l{j}'}<=window for window in windows) for i in range(81) for j in range(i+1,81))


@pytest.mark.parametrize('corrupt',['missing','duplicate','unknown','cross_domain','dangling'])
def test_invalid_merge_is_rejected_without_losing_inputs(corrupt):
    from knowledge import ResponseFormatError
    records=source(2);records[1]['domain']='research';original=copy.deepcopy(records)
    def bad(values,items,attempt):
        if corrupt=='missing':values.pop()
        elif corrupt=='duplicate':values[1]=values[0].copy()
        elif corrupt=='unknown':values[1]['leader']='unknown'
        elif corrupt=='cross_domain':values[1]['leader']='l0'
        else:values[0]['leader']='l1';values[1]['leader']='l0'
    request,calls=responder(bad)
    with pytest.raises(ResponseFormatError) as error:merge(records,request)
    assert records==original
    assert len(calls)==error.value.additional_api_calls==2


def test_cancel_before_next_window_prevents_more_calls():
    from concurrent.futures import CancelledError
    request,calls=responder()
    with pytest.raises(CancelledError) as error:merge(source(81),request,cancel=lambda:bool(calls))
    assert len(calls)==1 and error.value.additional_api_calls==1


def test_large_text_windows_have_a_character_budget_and_complete_pair_coverage():
    records=source(30)
    for row in records:row['text']='Supported method. '*100
    request,calls=responder()
    result=merge(records,request)
    assert result['lessons']==records
    assert all(sum(len(row['text']) for row in json.loads(body['messages'][0]['content'])['methods'])<=48000 for body in calls)
