import json
import runpy
from pathlib import Path
import pytest

from selfos.knowledge.records import validate_record, merge_records
from selfos.knowledge.settings import DEFAULT_SETTINGS

ROOT = Path(__file__).resolve().parents[1]


def fact(quote, value='designer', key='employment.role', scope=None, context=False):
    messages=[dict(id='m1',role='user',text=quote,timestamp='2026-11-12T10:00:00Z')]
    raw=dict(key=key,value=value,text=quote,domain='personal',kind='user_fact',
             source_ids=['m1'],evidence=quote)
    if scope is not None: raw['scope']=scope
    if context:
        messages.append(dict(id='m2',role='assistant',text='That helps the project.',timestamp='2026-11-13T10:00:00Z'))
        raw['source_ids'].append('m2')
    return validate_record(raw,dict(messages=messages,project_id='demo'))


def test_frozen_personal_fact_boundary_cases_are_addressed():
    evaluate=runpy.run_path(str(ROOT/'evals/run_personal_fact_holdout.py'))['evaluate']
    report=evaluate(json.loads((ROOT/'evals/personal_fact_holdout.json').read_text())['cases'])
    assert report['false_positive']==0
    assert report['false_negative']==0
    assert report['structural_source_traceability']==1


def test_context_does_not_support_or_downgrade_a_direct_fact():
    record=fact('I work as a designer.',context=True)
    assert record['kind']=='user_fact'
    assert record['supporting_source_ids']==['m1']
    assert record['context_source_ids']==['m2']
    assert record['observed_at']=='2026-11-12T10:00:00Z'


def test_same_role_relation_in_distinct_scopes_coexists_without_conflict():
    state={}
    for value,scope in [('designer','work'),('treasurer','volunteer')]:
        record=fact(f'I am a {value} in my {scope} activity.',value,
                    scope=dict(type='activity',id=scope))
        merge_records(state,'personal_facts',[record],DEFAULT_SETTINGS)
    assert len(state['personal_facts'])==2
    assert all(not r.get('conflict') for r in state['personal_facts'])


def test_equivalent_facts_keep_every_direct_support_and_context():
    state={}
    a=fact('I work as a designer.',context=True)
    b=fact('I am a designer.')
    b['source_ids']=['m3'];b['supporting_source_ids']=['m3']
    b['supporting_observations'][0]['source_id']='m3'
    merge_records(state,'personal_facts',[a,b],DEFAULT_SETTINGS)
    result=state['personal_facts'][0]
    assert set(result['supporting_source_ids'])=={'m1','m3'}
    assert result['context_source_ids']==['m2']
    assert len(result['supporting_observations'])==2


def test_preference_and_measurement_are_preserved_with_category_warning_in_history():
    for quote,key,value in [('I prefer diagrams when learning.','learning.format','diagrams'),
                            ('My temperature was 38 C this morning.','health.temperature','38 C')]:
        state={}
        merge_records(state,'personal_facts',[fact(quote,value,key)],DEFAULT_SETTINGS)
        assert not state['personal_facts']
        assert state['records_history'][0]['retention_reason'] in ('preference_claim','dated_observation')


def test_fact_schema_and_context_resolution_share_the_one_pass_protocol():
    from selfos.knowledge.evidence import output_schema, resolve_evidence
    schema=output_schema({'m1':'s1','m2':'s2'},{'s1:e1':('m1','I work as a designer.')},8)
    item=schema['properties']['personal_facts']['items']
    assert {'scope','claim_type','context_source_ids'} <= set(item['required'])
    result={'personal_facts':[dict(evidence_id='s1:e1',context_source_ids=['s2'])]}
    resolve_evidence(result,{'s1:e1':('m1','I work as a designer.')},{'s1':'m1','s2':'m2'})
    assert result['personal_facts'][0]['source_ids']==['m1','m2']


def test_fact_scope_and_support_categories_are_exposed_without_inventing_legacy_support(tmp_path):
    from selfos.app.library import list_knowledge, knowledge_detail
    record=fact('I work as a designer.',scope=dict(type='activity',id='work'),context=True)
    (tmp_path/'.knowledge_pipeline.json').write_text(json.dumps({'personal_facts':[record]}))
    row=list_knowledge(tmp_path,category='personal_facts')['items'][0]
    assert row['scope']=='work'
    item=knowledge_detail(tmp_path,row['id'])['item']
    assert item['supporting_source_ids']==['m1']
    assert item['context_source_ids']==['m2']


def test_typed_unknown_fact_is_archived_without_inventing_certainty():
    record=fact('I work as a designer.')
    record['claim_type']='unknown'
    state={};merge_records(state,'personal_facts',[record],DEFAULT_SETTINGS)
    assert not state['personal_facts']
    assert state['records_history'][0]['retention_reason']=='uncertain_personal_claim'


@pytest.mark.parametrize('quote',[
    'I am not a teacher.',
    'If I were a teacher, I would use this tool.',
    'An AI wrote this fictional profile: I am a teacher.',
])
def test_negative_hypothetical_and_inline_ai_profiles_do_not_become_current_roles(quote):
    state={};merge_records(state,'personal_facts',[fact(quote,'teacher')],DEFAULT_SETTINGS)
    assert not state['personal_facts']


def test_unrelated_value_is_not_supported_merely_by_an_exact_quote():
    state={};merge_records(state,'personal_facts',[fact('I work as a designer.','surgeon')],DEFAULT_SETTINGS)
    assert not state['personal_facts']


def test_facts_keep_tied_conflict_sources_in_each_arrival_order():
    for values in [('designer','teacher'),('teacher','designer')]:
        state={}
        for index,value in enumerate(values):
            record=fact(f'I work as a {value}.',value)
            record['source_ids']=[f'm{index+1}']
            record['supporting_source_ids']=[f'm{index+1}']
            record['supporting_observations'][0]['source_id']=f'm{index+1}'
            merge_records(state,'personal_facts',[record],DEFAULT_SETTINGS)
        assert all(set(r['conflict_source_ids'])=={'m1','m2'} for r in state['personal_facts'])


def test_positive_clause_is_not_rejected_due_to_an_unrelated_negation():
    quote='I do not manage the office; I work as a designer.'
    state={};merge_records(state,'personal_facts',[fact(quote)],DEFAULT_SETTINGS)
    assert len(state['personal_facts'])==1


def test_markdown_distinguishes_direct_support_from_context():
    from selfos.storage.records import managed_content
    record=fact('I work as a designer.',context=True)
    text=managed_content('', 'Facts',[record],'personal_facts').decode()
    assert 'Supporting sources: m1' in text
    assert 'Context sources: m2' in text


def test_project_alias_migrates_fact_scopes_and_cached_summaries(tmp_path):
    from selfos.app.pipeline import register_project_aliases
    import copy
    record=fact('I work as a designer.',scope=dict(type='project',id='current-project'))
    state={'personal_facts':[record], 'cards':{},'sources':{},
           'summaries':{'saved':{'project':None,'lessons':[],'personal_facts':[copy.deepcopy(record)]}}}
    (tmp_path/'.knowledge_pipeline.json').write_text(json.dumps(state))
    register_project_aliases(tmp_path,{'demo':'canonical'})
    updated=json.loads((tmp_path/'.knowledge_pipeline.json').read_text())
    assert updated['personal_facts'][0]['scope']=='canonical'
    assert updated['summaries']['saved']['personal_facts'][0]['scope']=='canonical'


def test_new_equivalent_support_updates_all_conflict_source_links():
    state={}
    for index,value in enumerate(('designer','teacher','designer')):
        record=fact(f'I work as a {value}.',value)
        record['source_ids']=[f'm{index+1}'];record['supporting_source_ids']=[f'm{index+1}']
        record['supporting_observations'][0]['source_id']=f'm{index+1}'
        merge_records(state,'personal_facts',[record],DEFAULT_SETTINGS)
    assert all(set(r['conflict_source_ids'])=={'m1','m2','m3'} for r in state['personal_facts'])


def test_context_identical_to_assistant_quote_does_not_promote_its_attribution():
    from selfos.knowledge.evidence import resolve_evidence
    quote='I work as a designer.'
    result={'personal_facts':[dict(key='employment.role',value='designer',text=quote,domain='personal',
              kind='user_fact',evidence_id='s1:e1',context_source_ids=['s2'])]}
    resolve_evidence(result,{'s1:e1':('m1',quote)},{'s1':'m1','s2':'m2'})
    record=validate_record(result['personal_facts'][0],{'messages':[
        dict(id='m1',role='assistant',text=quote),dict(id='m2',role='user',text=quote)]})
    assert record['kind']=='inference'
    assert record['supporting_source_ids']==['m1']
    assert record['context_source_ids']==['m2']


def test_alias_scope_collisions_are_reconsolidated_and_marked(tmp_path):
    from selfos.app.pipeline import register_project_aliases
    records=[]
    for index,(value,scope) in enumerate([('designer','a'),('teacher','b')]):
        record=fact(f'I work as a {value}.',value)
        record.update(scope_type='project',scope=scope,source_ids=[f'm{index}'],supporting_source_ids=[f'm{index}'])
        records.append(record)
    state={'personal_facts':records,'cards':{},'sources':{}}
    (tmp_path/'.knowledge_pipeline.json').write_text(json.dumps(state))
    register_project_aliases(tmp_path,{'a':'canonical','b':'canonical'})
    updated=json.loads((tmp_path/'.knowledge_pipeline.json').read_text())
    assert all(r.get('conflict') for r in updated['personal_facts'])


@pytest.mark.parametrize('quote',[
    'I prefer diagrams; I work as a designer.',
    'I do not manage the office, but I work as a designer.',
])
def test_other_clause_does_not_pollute_an_independent_direct_fact(quote):
    state={};merge_records(state,'personal_facts',[fact(quote)],DEFAULT_SETTINGS)
    assert len(state['personal_facts'])==1


def test_legacy_observed_date_survives_older_equivalent_evidence():
    old=fact('I work as a designer.')
    old.pop('supporting_observations');old.pop('supporting_source_ids');old.pop('context_source_ids')
    old['observed_at']='2026-11-13T10:00:00Z'
    state={'personal_facts':[old]}
    merge_records(state,'personal_facts',[fact('I am a designer.')],DEFAULT_SETTINGS)
    record=state['personal_facts'][0]
    assert record['observed_at']=='2026-11-13T10:00:00Z'
    assert record['legacy_observed_at']==['2026-11-13T10:00:00Z']


def test_invalid_claim_type_fails_validation_before_pipeline_merge():
    record=fact('I work as a designer.');record['claim_type']='made-up'
    with pytest.raises(ValueError,match='claim type'):
        validate_record(record,{'messages':[dict(id='m1',role='user',text=record['evidence'])]})


def test_legacy_explicit_context_cannot_support_same_text_quotation():
    quote='I work as a designer.'
    raw=dict(key='employment.role',value='designer',text=quote,domain='personal',kind='user_fact',
             source_ids=['m1','m2'],context_source_ids=['m2'],evidence=quote)
    record=validate_record(raw,{'messages':[dict(id='m1',role='assistant',text=quote),dict(id='m2',role='user',text=quote)]})
    assert record['kind']=='inference'
