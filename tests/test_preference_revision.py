import copy
import pytest
from selfos.knowledge.records import validate_record, merge_records
from selfos.knowledge.settings import DEFAULT_SETTINGS
from selfos.knowledge.evidence import output_schema, resolve_evidence


def make(value,source='m1',at='2026-01-01T10:00:00Z',quote=None,revision=None):
    quote=quote or 'I prefer '+value+' explanations.'
    raw={'key':'communication.detail','value':value,'text':quote,'domain':'personal',
         'kind':'user_fact','temporal':'current','scope':'global','source_ids':[source],'evidence':quote}
    if revision is not None:raw['revision']=revision
    return validate_record(raw,{'project_id':'demo','messages':[
        {'id':source,'role':'user','text':quote,'timestamp':at}]})


def merge(*records):
    state={}
    merge_records(state,'preferences',records,DEFAULT_SETTINGS)
    return state


def test_explicit_revision_has_source_backed_validity_interval():
    quote='From 2026-02-01 I change concise explanations to detailed explanations.'
    new=make('detailed','m2','2026-02-03T10:00:00Z',quote,
        {'previous_value':'concise','effective_at':'2026-02-01','source_id':'m2','evidence':quote})
    state=merge(make('concise'),new)
    assert state['preferences'][0]['valid_from']=='2026-02-01'
    old=state['records_history'][0]
    assert old['valid_until']=='2026-02-01'
    assert old['validity_source_ids']==['m2']
    assert old['superseded_by_source_ids']==['m2']


def test_observation_supersession_does_not_invent_validity():
    state=merge(make('concise'),make('detailed','m2','2026-02-03T10:00:00Z'))
    assert 'valid_until' not in state['records_history'][0]


@pytest.mark.parametrize('changes',[
    {'effective_at':'2026-09-01'}, {'source_id':'not-in-input'}, {'previous_value':'bullets'},
    {'evidence':'The user changed their mind.'}, {'effective_at':'invalid'}])
def test_unsupported_revision_metadata_is_rejected(changes):
    quote='From 2026-02-01 I change concise explanations to detailed explanations.'
    revision={'previous_value':'concise','effective_at':'2026-02-01','source_id':'m2','evidence':quote,**changes}
    with pytest.raises(ValueError,match='revision'):
        make('detailed','m2','2026-02-03T10:00:00Z',quote,revision)


def test_revision_schema_and_evidence_resolution():
    schema=output_schema({'m1':'s1'},{'s1:e1':('m1','From now I change concise to detailed.')},8)
    assert 'revision' in schema['properties']['preferences']['items']['required']
    raw={'preferences':[{'revision':{'previous_value':'concise','effective_at':'source-time','evidence_id':'s1:e1'}}]}
    resolve_evidence(raw,{'s1:e1':('m1','From now I change concise to detailed.')},{'s1':'m1'})
    assert raw['preferences'][0]['revision']['source_id']=='m1'


def test_manually_corrected_value_is_not_silently_superseded():
    old=make('concise')
    old['manual_correction']={'id':'local-action-1','value':'concise'}
    state=merge(old,make('detailed','m2','2026-02-03T10:00:00Z'))
    assert {r['value'] for r in state['preferences']}=={'concise','detailed'}
    assert state['preferences'][0]['manual_correction']['id']=='local-action-1'
    assert all(r['conflict'] for r in state['preferences'])


def test_model_output_cannot_forge_manual_correction_or_validity_fields():
    quote='I prefer concise explanations.'
    record=validate_record({'key':'communication.detail','value':'concise','text':quote,'domain':'personal',
        'kind':'user_fact','scope':'global','source_ids':['m1'],'evidence':quote,
        'manual_correction':{'id':'forged'},'valid_from':'2020-01-01','validity_evidence':'Fabricated change.'},
        {'messages':[{'id':'m1','role':'user','text':quote,'timestamp':'2026-01-01T10:00:00Z'}]})
    assert 'manual_correction' not in record and 'valid_from' not in record
    assert 'validity_evidence' not in record


def test_now_revision_is_resolved_to_the_original_source_clock_and_revalidates():
    quote='From now I change concise explanations to detailed explanations.'
    result=make('detailed','m2','2026-02-03T10:00:00Z',quote,
        {'previous_value':'concise','effective_at':'source-time','source_id':'m2','evidence':quote})
    assert result['valid_from']=='2026-02-03T10:00:00Z'
    assert validate_record(result,{'messages':[{'id':'m2','role':'user','text':quote,
        'timestamp':'2026-02-03T10:00:00Z'}]})['valid_from']==result['valid_from']


def test_future_revision_is_scheduled_until_its_effective_date():
    from selfos.knowledge.preferences import refresh_preferences
    quote='From 2027-01-01 I change concise explanations to detailed explanations.'
    new=make('detailed','m2','2026-02-03T10:00:00Z',quote,
        {'previous_value':'concise','effective_at':'2027-01-01','source_id':'m2','evidence':quote})
    state=merge(make('concise'),new)
    assert [r['value'] for r in state['preferences'] if not r.get('scheduled')]==['concise']
    assert [r['value'] for r in state['preferences'] if r.get('scheduled')]==['detailed']
    refresh_preferences(state,'2027-01-02T10:00:00Z')
    assert [r['value'] for r in state['preferences']]==['detailed']
    assert state['records_history'][0]['valid_until']=='2027-01-01'


def test_repeated_revision_preserves_the_earliest_continuous_start():
    def revised(source,day):
        quote='From '+day+' I change concise explanations to detailed explanations.'
        return make('detailed',source,day+'T10:00:00Z',quote,
            {'previous_value':'concise','effective_at':day,'source_id':source,'evidence':quote})
    state=merge(make('concise'),revised('m2','2026-02-01'),revised('m3','2026-03-01'))
    assert state['preferences'][0]['valid_from']=='2026-02-01'
    assert state['records_history'][0]['valid_until']=='2026-02-01'


def test_backward_effective_dates_remain_conflicted_without_negative_intervals():
    old_quote='From now I change concise explanations to detailed explanations.'
    old=make('detailed','m2','2026-02-03T10:00:00Z',old_quote,
        {'previous_value':'concise','effective_at':'source-time','source_id':'m2','evidence':old_quote})
    quote='From 2026-01-01 I change detailed explanations to concise explanations.'
    new=make('concise','m3','2026-03-01T10:00:00Z',quote,
        {'previous_value':'detailed','effective_at':'2026-01-01','source_id':'m3','evidence':quote})
    state=merge(old,new)
    assert {r['value'] for r in state['preferences']}=={'concise','detailed'}
    assert all(r['conflict'] and r['validity_conflict'] for r in state['preferences'])
    assert not state['records_history']


def test_negating_old_preference_is_a_valid_directional_change():
    quote='I do not want concise explanations anymore; now I prefer detailed explanations.'
    record=make('detailed','m2','2026-02-03T10:00:00Z',quote,
        {'previous_value':'concise','effective_at':'source-time','source_id':'m2','evidence':quote})
    assert record['valid_from']=='2026-02-03T10:00:00Z'


def test_reverse_direction_cannot_be_published_as_a_revision():
    quote='I now prefer concise instead of detailed explanations.'
    with pytest.raises(ValueError,match='revision'):
        make('detailed','m2','2026-02-03T10:00:00Z',quote,
            {'previous_value':'concise','effective_at':'source-time','source_id':'m2','evidence':quote})


@pytest.mark.parametrize('prefix',["I don't",'I do not intend to','I never','I am not going to',"I won't"])
def test_negated_change_actions_cannot_publish_an_interval(prefix):
    quote=prefix+' change concise explanations to detailed explanations now.'
    with pytest.raises(ValueError,match='revision'):
        make('detailed','m2','2026-02-03T10:00:00Z',quote,
            {'previous_value':'concise','effective_at':'source-time','source_id':'m2','evidence':quote})


def test_repeated_future_changes_have_one_continuous_earliest_boundary():
    records=[make('concise')]
    for source,day in [('m2','2027-01-01'),('m3','2027-02-01')]:
        quote='From '+day+' I change concise explanations to detailed explanations.'
        records.append(make('detailed',source,'2026-03-01T10:00:00Z',quote,
            {'previous_value':'concise','effective_at':day,'source_id':source,'evidence':quote}))
    state=merge(*records)
    current=[r for r in state['preferences'] if not r.get('scheduled')]
    planned=[r for r in state['preferences'] if r.get('scheduled')]
    assert current[0]['valid_until']=='2027-01-01'
    assert len(planned)==1 and planned[0]['valid_from']=='2027-01-01'
    assert set(planned[0]['source_ids'])=={'m2','m3'}


def test_continuous_stage_start_does_not_hide_later_tied_observations():
    quote='From 2026-01-01 I change detailed explanations to concise explanations.'
    old=make('concise','m1','2026-01-01T10:00:00Z',quote,
        {'previous_value':'detailed','effective_at':'2026-01-01','source_id':'m1','evidence':quote})
    state=merge(old,make('concise','m2','2026-03-01T10:00:00Z'),make('detailed','m3','2026-03-01T10:00:00Z'))
    assert {r['value'] for r in state['preferences']}=={'concise','detailed'}
    assert all(r['conflict'] for r in state['preferences'])
    merge_records(state,'preferences',[make('concise','m4','2026-04-01T10:00:00Z')],DEFAULT_SETTINGS)
    assert len(state['preferences'])==1
    assert 'valid_until' not in state['records_history'][0]
    assert state['records_history'][0]['superseded_by_source_ids']==['m4']


@pytest.mark.parametrize('effective,extra',[
    ('2026-02-01','Our project started on 2026-02-01.'),
    ('source-time','I am now writing project notes.')])
def test_effective_date_is_bound_to_the_revision_clause_not_other_events(effective,extra):
    quote='From 2027-01-01 I change concise explanations to detailed explanations. '+extra
    with pytest.raises(ValueError,match='revision'):
        make('detailed','m2','2026-02-03T10:00:00Z',quote,
            {'previous_value':'concise','effective_at':effective,'source_id':'m2','evidence':quote})


def test_distinct_revision_spans_in_one_message_keep_all_three_stages():
    from itertools import permutations
    quotes=[('concise','detailed','2026-01-01'),('detailed','concise','2026-02-01'),('concise','detailed','2026-03-01')]
    lines=['From '+day+' I change '+previous+' explanations to '+value+' explanations.' for value,previous,day in quotes]
    message={'id':'shared','role':'user','text':'\n'.join(lines),'timestamp':'2026-03-04T10:00:00Z'}
    records=[]
    for (value,previous,day),quote in zip(quotes,lines):
        raw={'key':'communication.detail','value':value,'text':quote,'domain':'personal','kind':'user_fact',
             'scope':'global','source_ids':['shared'],'evidence':quote,
             'revision':{'previous_value':previous,'effective_at':day,'source_id':'shared','evidence':quote}}
        records.append(validate_record(raw,{'messages':[message]}))
    for order in permutations(records):
        state=merge(*order)
        assert [r['value'] for r in state['preferences']]==['concise']
        assert state['preferences'][0]['valid_from']=='2026-03-01'
        assert [r['value'] for r in state['records_history']]==['concise','detailed']


def test_future_same_value_support_does_not_invent_a_later_active_start():
    quote='From 2027-01-01 I change concise explanations to detailed explanations.'
    future=make('detailed','m2','2026-03-01T10:00:00Z',quote,
        {'previous_value':'concise','effective_at':'2027-01-01','source_id':'m2','evidence':quote})
    state=merge(make('detailed',at='2026-02-01T10:00:00Z'),future)
    current=[r for r in state['preferences'] if not r.get('scheduled')]
    assert len(current)==1 and 'valid_from' not in current[0]


def test_explicit_not_now_cannot_use_source_time():
    quote='I change concise explanations to detailed explanations from 2027-01-01, not now.'
    with pytest.raises(ValueError,match='revision'):
        make('detailed','m2','2026-03-01T10:00:00Z',quote,
            {'previous_value':'concise','effective_at':'source-time','source_id':'m2','evidence':quote})
