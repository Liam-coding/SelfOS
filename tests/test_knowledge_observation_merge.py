import copy,json
import pytest


def observation(text,source,**extra):
    return {'text':text,'source_ids':[source],'domain':'work','kind':'inference',**extra}


def responder(change=None):
    calls=[]
    def request(req,**kwargs):
        body=json.loads(req.data);calls.append(body);items=json.loads(body['messages'][0]['content'])['observations']
        values=[{'id':row['id'],'leader':row['id'],'reason':'Distinct observation.'} for row in items]
        if change:change(values,items,len(calls))
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return json.dumps({'content':[{'type':'tool_use','name':'group_observations','input':{'groups':values}}]}).encode()
        return Response()
    return request,calls


def merge(records,request,cancel=lambda:False):
    from selfos.providers.reviews.observations import merge_project_observations
    return merge_project_observations(records,'test','https://example.test',open_request=request,cancel=cancel)


def join(values,items,attempt):values[1]['leader']=values[0]['id']


def test_equivalent_project_observations_merge_without_rewriting_or_losing_sources():
    records=[observation('Paragraphs stay immutable; cue invalidation controls retrieval.','m0'),
             observation('Retrieval annotations change without deleting original paragraphs.','m1')]
    original=copy.deepcopy(records);request,calls=responder(join);result=merge(records,request)
    assert records==original and len(result['observations'])==1
    assert result['observations'][0]['text']==records[0]['text']
    assert result['observations'][0]['source_ids']==['m0','m1']
    assert result['calls']==len(calls)==1 and len(result['audit'])==2


@pytest.mark.parametrize('field,first,second',[
    ('project_id','alpha','beta'),('configuration_id','baseline','trial'),
    ('event_time','2026-10-01','2026-11-01'),('temporal','historical','current'),
    ('status','proposed','implemented')])
def test_explicitly_different_project_conditions_cannot_be_merged(field,first,second):
    from knowledge import ResponseFormatError
    records=[observation('Same description','m0',**{field:first}),observation('Same description','m1',**{field:second})]
    request,calls=responder(join)
    with pytest.raises(ResponseFormatError,match='scope') as error:merge(records,request)
    assert len(calls)==error.value.additional_api_calls==2


def test_different_numeric_results_cannot_disappear_in_canonical_text():
    from knowledge import ResponseFormatError
    records=[observation('Trial used a 0.15 gap.','m0'),observation('Trial used a 0.20 gap.','m1')]
    request,_=responder(join)
    with pytest.raises(ResponseFormatError,match='numeric'):merge(records,request)


def test_complete_before_after_description_can_cover_a_narrower_observation():
    records=[observation('Baseline F1 0.6109; trial F1 0.6264.','m0'),observation('Baseline F1 0.6109.','m1')]
    request,_=responder(join);result=merge(records,request)
    assert len(result['observations'])==1
    assert '0.6264' in result['observations'][0]['text']


def test_source_dates_can_differ_but_both_remain_in_audit():
    records=[observation('Immutable paragraphs','m0',observed_at='2026-10-01'),
             observation('Immutable paragraphs','m1',observed_at='2026-11-01')]
    request,_=responder(join);result=merge(records,request)
    assert result['observations'][0]['source_ids']==['m0','m1']
    assert [row['observed_at'] for row in result['audit']]==['2026-10-01','2026-11-01']


def test_pre_cancelled_observation_merge_makes_no_call():
    from concurrent.futures import CancelledError
    request,calls=responder()
    with pytest.raises(CancelledError):merge([observation('A','m0'),observation('B','m1')],request,cancel=lambda:True)
    assert not calls


def test_distinct_observations_survive_without_a_count_quota():
    records=[observation(f'Distinct outcome {i}','m'+str(i)) for i in range(81)]
    request,calls=responder();result=merge(records,request)
    assert result['observations']==records and len(calls)==3


def test_later_window_cannot_replace_a_complete_prior_canonical_with_a_narrower_one():
    records=[observation(f'Distinct outcome {i}','m'+str(i)) for i in range(81)]
    records[0]['text']='Baseline gap 0.15; trial gap 0.20.'
    records[1]['text']=records[80]['text']='Baseline gap 0.15.'
    def group(values,items,attempt):
        indexed={value['id']:value for value in values}
        if attempt==1:indexed['o1']['leader']='o0'
        elif attempt==2:indexed['o1']['leader']='o80'
    request,_=responder(group);result=merge(records,request)
    combined=next(row for row in result['observations'] if 'm0' in row['source_ids'])
    assert combined['text']==records[0]['text']
    assert combined['source_ids']==['m0','m1','m80']


def test_numeric_formatting_equivalence_does_not_create_a_false_conflict():
    records=[observation('Scanned 3,544 cues at a 0.15 gap.','m0'),observation('Scanned 3544 cues at a .15 gap.','m1')]
    request,_=responder(join);assert len(merge(records,request)['observations'])==1


def test_percent_and_percentage_point_wording_preserves_the_same_quantity():
    records=[observation('Input reduced 41 percent; F1 changed 11.5 percentage points.','m0'),
             observation('Input reduced 41%; F1 changed 11.5pp.','m1')]
    request,_=responder(join);assert len(merge(records,request)['observations'])==1


def test_incompatible_prior_clusters_remain_separate_with_all_measurements():
    records=[observation(f'Distinct outcome {i}','m'+str(i)) for i in range(81)]
    records[0]['text']='Baseline 0.15; trial 0.20.';records[40]['text']='Baseline 0.15; trial 0.30.'
    for index in (1,41,80):records[index]['text']='Baseline 0.15.'
    def group(values,items,attempt):
        indexed={value['id']:value for value in values}
        if attempt==1:indexed['o1']['leader']='o0';indexed['o41']['leader']='o40'
        elif attempt==2:indexed['o1']['leader']='o80'
        else:indexed['o41']['leader']='o80'
    request,_=responder(group);result=merge(records,request)
    first=next(row for row in result['observations'] if 'm0' in row['source_ids'])
    second=next(row for row in result['observations'] if 'm40' in row['source_ids'])
    assert first['text']==records[0]['text'] and second['text']==records[40]['text']
    assert any(not row['merge_applied'] for row in result['audit'])


@pytest.mark.parametrize('first,second',[
    ('Trial delta 0.0013.','Trial delta -0.0013.'),
    ('Trial delta 0.0013.','Trial delta −0.0013.'),
    ('Run identifier 123456789012345678901234567890.','Run identifier 123456789012345678901234567891.')])
def test_numeric_direction_and_long_identifiers_are_not_lost(first,second):
    from knowledge import ResponseFormatError
    records=[observation(first,'m0'),observation(second,'m1')]
    request,_=responder(join)
    with pytest.raises(ResponseFormatError,match='numeric'):merge(records,request)
