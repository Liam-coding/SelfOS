import copy,json
import pytest


def review():
    from knowledge_lesson_review import review_reusable_records
    return review_reusable_records


def records(count=3):
    return {'project':{},'lessons':[{'text':['Local endpoint configuration','Atomic checkpoint mechanism','Run sample now'][i%3],
        'source_ids':[f'm{i}'],'domain':'work','kind':'inference'} for i in range(count)],'observations':[]}


def responder(transform=None):
    calls=[]
    def request(req,**kwargs):
        body=json.loads(req.data);calls.append(body);items=json.loads(body['messages'][0]['content'])['candidates']
        verdicts=[]
        for item in items:
            action={'Local endpoint configuration':'observation','Atomic checkpoint mechanism':'lesson','Run sample now':'discard'}[item['text']]
            verdicts.append({'id':item['id'],'action':action,'lesson_text':item['text'] if action=='lesson' else '',
                'observation_text':item['text'] if action=='observation' else '', 'reason':'Classified against supplied candidate scope.'})
        if transform:verdicts=transform(verdicts)
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return json.dumps({'content':[{'type':'tool_use','name':'route_knowledge','input':{'verdicts':verdicts}}]}).encode()
        return Response()
    return request,calls


def test_routes_candidates_with_original_sources_and_without_mutating_input():
    source=records();original=copy.deepcopy(source);request,calls=responder()
    result=review()(source,'test','https://example.test',open_request=request)
    assert source==original
    assert result['lessons'][0]['source_ids']==['m1']
    assert result['observations'][0]['source_ids']==['m0']
    assert len(result['lessons'])==len(result['observations'])==1
    assert result['_additional_api_calls']==1
    assert len(result['_lesson_review'])==3


def test_missing_or_duplicate_verdict_is_rejected():
    from knowledge import ResponseFormatError
    for transform in [lambda values:values[:-1],lambda values:[values[0]]*len(values)]:
        request,_=responder(transform)
        with pytest.raises(ResponseFormatError):review()(records(),'test','https://example.test',open_request=request)


def test_review_batches_cover_every_candidate_without_final_quota():
    request,calls=responder();result=review()(records(21),'test','https://example.test',open_request=request)
    assert len(calls)==2 and len(result['_lesson_review'])==21
    assert result['_additional_api_calls']==2
    assert all(len(json.loads(body['messages'][0]['content'])['candidates'])<=20 for body in calls)


def test_inconsistent_routing_is_rejected_and_failed_call_count_is_kept():
    from knowledge import ResponseFormatError
    def inconsistent(values):
        values[0]['action']='lesson'
        return values
    request,_=responder(inconsistent)
    with pytest.raises(ResponseFormatError,match='disagree') as captured:
        review()(records(),'test','https://example.test',open_request=request)
    assert captured.value.additional_api_calls==2
    assert len(captured.value.routing_diagnostics)==2
    assert captured.value.raw_response


def test_complete_json_array_string_verdicts_are_normalized():
    request,_=responder(lambda values:json.dumps(values))
    result=review()(records(),'test','https://example.test',open_request=request)
    assert len(result['_lesson_review'])==3


def test_semantic_group_uses_canonical_method_and_unions_sources():
    source=records(2)
    source['lessons'][0]['text']='Atomic checkpoint mechanism'
    def group(values):
        for value in values:value['lesson_group']='c0'
        values[0]['lesson_text']='Use atomic checkpoints with source validation for safe resumption.'
        values[1]['lesson_text']='Persist checkpoints atomically and validate provenance before resuming.'
        return values
    request,_=responder(group);result=review()(source,'test','https://example.test',open_request=request)
    assert len(result['lessons'])==1
    assert result['lessons'][0]['source_ids']==['m0','m1']
    assert result['lessons'][0]['text']=='Use atomic checkpoints with source validation for safe resumption.'


def test_group_member_can_reference_leader_without_repeating_method_text():
    source=records(2);source['lessons'][0]['text']='Atomic checkpoint mechanism'
    def group(values):
        for value in values:value['lesson_group']='c0'
        values[1]['lesson_text']=''
        return values
    request,_=responder(group)
    result=review()(source,'test','https://example.test',open_request=request)
    assert len(result['lessons'])==1
    assert result['lessons'][0]['source_ids']==['m0','m1']


def test_empty_group_leader_is_rejected():
    from knowledge import ResponseFormatError
    def group(values):
        values[1]['lesson_text']='';values[1]['lesson_group']='c1'
        return values
    request,_=responder(group)
    with pytest.raises(ResponseFormatError):review()(records(),'test','https://example.test',open_request=request)


def test_both_group_member_keeps_its_observation_and_inherits_method():
    source=records(2);source['lessons'][0]['text']='Atomic checkpoint mechanism'
    def group(values):
        for value in values:value['lesson_group']='c0'
        values[1].update(action='both',lesson_text='',observation_text='This project resumed checkpoint A.')
        return values
    request,_=responder(group)
    result=review()(source,'test','https://example.test',open_request=request)
    assert result['lessons'][0]['source_ids']==['m0','m1']
    assert result['observations'][0]['source_ids']==['m1']


def test_failed_cross_batch_grouping_includes_all_call_costs(monkeypatch):
    from knowledge import ResponseFormatError
    def distinct(values):
        for value in values:
            if value['action']=='lesson':value['lesson_text']+=' '+value['id']
        return values
    request,calls=responder(distinct)
    def failed(*args,**kwargs):
        error=ResponseFormatError('Invalid method grouping');error.additional_api_calls=2
        raise error
    monkeypatch.setattr('knowledge_method_merge.merge_reviewed_methods',failed)
    with pytest.raises(ResponseFormatError) as error:
        review()(records(21),'test','https://example.test',open_request=request)
    assert len(calls)==2 and error.value.additional_api_calls==4


def test_semantic_group_cannot_point_to_unknown_candidate():
    from knowledge import ResponseFormatError
    def group(values):
        values[1]['lesson_group']='unknown'
        return values
    request,_=responder(group)
    with pytest.raises(ResponseFormatError,match='group'):review()(records(),'test','https://example.test',open_request=request)


def test_stop_between_batches_does_not_schedule_another_review():
    from concurrent.futures import CancelledError
    stopped=[];original,calls=responder()
    def request(req,**kwargs):
        response=original(req,**kwargs);stopped.append(True);return response
    source=records(21);previous=copy.deepcopy(source)
    with pytest.raises(CancelledError) as captured:
        review()(source,'test','https://example.test',open_request=request,cancel=lambda:bool(stopped))
    assert len(calls)==1 and captured.value.additional_api_calls==1
    assert source==previous


def test_pre_cancelled_routing_makes_no_request():
    from concurrent.futures import CancelledError
    request,calls=responder()
    with pytest.raises(CancelledError):review()(records(),'test','https://example.test',open_request=request,cancel=lambda:True)
    assert not calls


def test_invalid_later_batch_retries_only_that_batch_with_feedback():
    good,calls=responder()
    def request(req,**kwargs):
        response=good(req,**kwargs)
        if len(calls)==2:
            response.read=lambda:json.dumps({'content':[{'type':'tool_use','name':'route_knowledge','input':{'verdicts':[]}}]}).encode()
        return response
    result=review()(records(21),'test','https://example.test',open_request=request)
    assert len(calls)==3 and result['_additional_api_calls']==3
    batches=[json.loads(body['messages'][0]['content']) for body in calls]
    assert batches[1]['candidates']==batches[2]['candidates']
    assert len(batches[0]['candidates'])==20
    assert 'cover every ID' in batches[2]['repair_feedback']
    assert result['_lesson_review_errors'][0]['batch_start']==20
    assert len(result['_lesson_review'])==21


def test_cancelled_repair_does_not_make_another_request():
    from concurrent.futures import CancelledError
    stopped=[];good,calls=responder(lambda values:[])
    def request(req,**kwargs):
        response=good(req,**kwargs);stopped.append(True);return response
    with pytest.raises(CancelledError) as captured:
        review()(records(),'test','https://example.test',open_request=request,cancel=lambda:bool(stopped))
    assert len(calls)==1 and captured.value.additional_api_calls==1


def test_review_merges_equivalent_methods_from_different_routing_batches():
    source=records(21)
    for index,row in enumerate(source['lessons']):row['text']=f'Supported method {index}'
    calls=[]
    def request(req,**kwargs):
        body=json.loads(req.data);calls.append(body);name=body['tools'][0]['name']
        payload=json.loads(body['messages'][0]['content'])
        if name=='route_knowledge':
            values=[{'id':r['id'],'action':'lesson','lesson_group':r['id'],'lesson_text':r['text'],
                     'observation_text':'','reason':'Transferable mechanism supplied.'} for r in payload['candidates']]
            checked={'verdicts':values}
        else:
            values=[{'id':r['id'],'leader':'l0' if r['id']=='l20' else r['id'],'reason':'Same mechanism.'}
                    for r in payload['methods']]
            checked={'groups':values}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return json.dumps({'content':[{'type':'tool_use','name':name,'input':checked}]}).encode()
        return Response()
    result=review()(source,'test','https://example.test',open_request=request)
    assert len(result['lessons'])==20
    assert result['lessons'][0]['source_ids']==['m0','m20']
    assert len(calls)==result['_additional_api_calls']==3
    assert len(result['_lesson_merges'])==21


def test_legacy_missing_domain_uses_the_existing_work_default_in_output():
    import copy
    value=records(1)
    value['lessons'][0].pop('domain',None)
    original=copy.deepcopy(value)
    request,_=responder()
    result=review()(value,'test','https://example.test',open_request=request)
    assert result['observations'][0]['domain']=='work'
    assert value==original


def test_routing_prompt_lists_only_same_domain_canonical_groups():
    value=records(2)
    value['lessons'][1]['domain']='research'
    request,calls=responder()
    review()(value,'test','https://example.test',open_request=request)
    candidates=json.loads(calls[0]['messages'][0]['content'])['candidates']
    assert candidates[0]['allowed_lesson_groups']==['c0']
    assert candidates[1]['allowed_lesson_groups']==['c1']
