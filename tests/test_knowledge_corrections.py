import copy
import pytest

from selfos.knowledge.corrections import apply_corrections, create_action, record_version


def record(value='concise', source='m1'):
    quote=f'I prefer {value} explanations.'
    return dict(key='communication.detail',value=value,text=quote,domain='personal',kind='user_fact',
                scope_type='global',scope='global',source_ids=[source],supporting_source_ids=[source],
                supporting_observations=[dict(source_id=source,evidence=quote,observed_at='2026-01-01T10:00:00Z')],
                observed_at='2026-01-01T10:00:00Z',evidence=quote)


def state(*records):
    return {'preferences':list(records),'sources':{r['source_ids'][0]:{'path':'synthetic.jsonl'} for r in records}}


def action(data, ledger, operation='edit', records=None, **fields):
    selected=records if records is not None else data['preferences'][:1]
    return create_action(data,ledger,{'action':operation,'ids':[record_version('preferences',r) for r in selected],**fields})


def test_manual_edit_does_not_rewrite_sources_or_claim_a_supporting_quote():
    data=state(record());before=copy.deepcopy(data)
    ledger=action(data,{},patch={'value':'balanced','text':'I prefer balanced explanations.'})
    view=apply_corrections(data,ledger)
    assert data==before
    assert view['sources']==before['sources']
    changed=view['preferences'][0]
    assert changed['value']=='balanced' and changed['kind']=='user_correction'
    assert changed['evidence']==before['preferences'][0]['evidence']
    assert changed['manual_correction']


def test_deleted_unchanged_evidence_is_suppressed_after_a_new_key_and_paraphrase():
    original=record();data=state(original)
    ledger=action(data,{},'delete')
    regenerated={**original,'key':'response.detail','value':'brief','text':'Likes short answers'}
    assert not apply_corrections(state(regenerated),ledger)['preferences']
    assert apply_corrections(state(regenerated),ledger)['correction_review']


def test_new_evidence_cannot_silently_replace_manual_correction():
    data=state(record())
    ledger=action(data,{},patch={'value':'balanced','text':'Balanced explanations'})
    incoming=state(record(),record('detailed','m2'))
    view=apply_corrections(incoming,ledger)
    assert {r['value'] for r in view['preferences']}=={'balanced','detailed'}
    assert all(r.get('conflict') for r in view['preferences'])


def test_merge_preserves_original_evidence_and_undo_restores_current_generated_state():
    a,b=record(),record('brief','m2');data=state(a,b)
    ledger=action(data,{},'merge',records=[a,b],patch={'value':'concise','text':'Concise explanations'})
    merged=apply_corrections(data,ledger)['preferences']
    assert len(merged)==1
    assert set(merged[0]['source_ids'])=={'m1','m2'}
    later=state(a,b,record('detailed','m3'))
    undone=create_action(later,ledger,{'action':'undo','action_id':ledger['actions'][0]['id']})
    assert len(apply_corrections(later,undone)['preferences'])==3


def test_undo_rejects_active_dependent_edit_without_losing_it():
    a,b=record(),record('brief','m2');data=state(a,b)
    ledger=action(data,{},'merge',records=[a,b],patch={'value':'concise','text':'Concise explanations'})
    view=apply_corrections(data,ledger)
    ledger=action(data,ledger,records=view['preferences'],patch={'value':'balanced','text':'Balanced explanations'})
    with pytest.raises(ValueError,match='dependent'):
        create_action(data,ledger,{'action':'undo','action_id':ledger['actions'][0]['id']})


def test_stale_version_and_evidence_patch_are_rejected():
    data=state(record())
    with pytest.raises(ValueError,match='version'):
        create_action(data,{},dict(action='delete',ids=['stale']))
    with pytest.raises(ValueError,match='editable'):
        action(data,{},patch={'evidence':'Invented quote'})


def test_legacy_unsourced_record_is_replaced_by_version_without_inventing_sources():
    original=record();original['source_ids']=[];original['supporting_source_ids']=[];original['supporting_observations']=[]
    data={'preferences':[original],'sources':{}}
    ledger=action(data,{},patch={'value':'balanced','text':'Balanced explanations'})
    view=apply_corrections(data,ledger)
    assert len(view['preferences'])==1
    assert view['preferences'][0]['source_ids']==[]


def test_derived_history_can_be_corrected_without_changing_project_source_state():
    from selfos.knowledge.history import history_records
    data={'cards':{'p':{'project_id':'p','title':'Synthetic project','domain':'work','decisions':[],
          'decision_history':['Use the earlier approach.'],'source_ids':['m1']}},'sources':{}}
    before=copy.deepcopy(data)
    historical=history_records(data)[0]
    ledger=create_action(data,{},dict(action='edit',ids=[record_version('history',historical)],
                         patch={'text':'Corrected historical description.'}))
    records=history_records(apply_corrections(data,ledger))
    assert len(records)==1 and records[0]['text']=='Corrected historical description.'
    assert data==before


def test_browser_options_restrict_merge_scope_and_explain_undo_dependencies():
    from selfos.knowledge.corrections import correction_options
    a,b=record(),record('brief','m2')
    other={**record('detailed','m3'),'scope_type':'activity','scope':'learning'}
    data=state(a,b,other)
    options=correction_options(data,{},record_version('preferences',a))
    assert [r['id'] for r in options['compatible']]==[record_version('preferences',b)]
    ledger=action(data,{},'merge',records=[a,b],patch={'value':'concise','text':'Concise explanations'})
    view=apply_corrections(data,ledger)
    merged=next(r for r in view['preferences'] if r.get('manual_correction'))
    ledger=action(data,ledger,records=[merged],patch={'value':'balanced','text':'Balanced explanations'})
    options=correction_options(data,ledger)
    assert not options['actions'][0]['can_undo']
    assert options['actions'][1]['can_undo']


def test_merging_all_conflicting_values_clears_the_resolved_conflict():
    a,b=record(),record('brief','m2')
    a.update(conflict=True,conflict_source_ids=['m1','m2'])
    b.update(conflict=True,conflict_source_ids=['m1','m2'])
    data=state(a,b)
    ledger=action(data,{},'merge',records=[a,b],patch={'value':'balanced','text':'Resolved preference'})
    assert not apply_corrections(data,ledger)['preferences'][0].get('conflict')


def test_deleted_action_history_keeps_original_quotes_and_source_references():
    from selfos.knowledge.corrections import correction_options
    data=state(record())
    ledger=action(data,{},'delete')
    original=correction_options(data,ledger)['actions'][0]['originals'][0]
    assert original['evidence']=='I prefer concise explanations.'
    assert original['source_ids']==['m1']


def test_project_correction_does_not_hide_another_project_sharing_source_context():
    from tests.test_project_knowledge_contract import card
    a,b=card(project_id='p1'),card(project_id='p2')
    data={'cards':{'p1':a,'p2':b}}
    ledger=create_action(data,{},dict(action='edit',ids=[record_version('projects',a)],patch={'text':'Corrected purpose'}))
    view=apply_corrections(data,ledger)
    assert set(view['cards'])=={'p1','p2'}
    assert view['cards']['p2']==b


def test_project_purpose_correction_keeps_new_generated_status_and_next_steps():
    from tests.test_project_knowledge_contract import card
    original=card(project_id='p1');data={'cards':{'p1':original}}
    ledger=create_action(data,{},dict(action='edit',ids=[record_version('projects',original)],patch={'text':'Corrected purpose'}))
    updated={**original,'status':'blocked','next_steps':['Resolve the new blocker.'],'source_ids':['m2']}
    view=apply_corrections({'cards':{'p1':updated}},ledger)
    assert view['cards']['p1']['intent']=='Corrected purpose'
    assert view['cards']['p1']['status']=='blocked'
    assert view['cards']['p1']['next_steps']==['Resolve the new blocker.']


def test_deleted_preference_cannot_reappear_as_archived_history():
    from selfos.knowledge.history import history_records
    original=record(); data=state(original)
    ledger=action(data,{},'delete')
    archived={**original,'original_category':'preferences','retention_reason':'superseded'}
    view=apply_corrections({'preferences':[],'records_history':[archived]},ledger)
    assert not history_records(view)


@pytest.mark.parametrize('aliases',[{'old':'canonical'},{'old':'middle','middle':'canonical'}])
def test_project_scope_correction_follows_alias_and_conflicts_with_new_evidence(aliases):
    original={**record(),'scope_type':'project','scope':'old'}
    data=state(original)
    ledger=action(data,{},patch={'value':'balanced','text':'Balanced explanations'})
    new={**record('detailed','m2'),'scope_type':'project','scope':'canonical'}
    view=apply_corrections({'preferences':[new],'project_aliases':aliases},ledger)
    assert {r['scope'] for r in view['preferences']}=={'canonical'}
    assert all(r.get('conflict') for r in view['preferences'])
