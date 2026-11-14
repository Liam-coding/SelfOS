"""Pure change comparison: no model, filesystem or personal sources."""
import copy
from tests.test_knowledge_corrections import record, state, action
from selfos.knowledge.corrections import create_action

NOW='2026-11-14T10:00:00Z'


def compare(before,after,before_ledger=None,after_ledger=None,**kwargs):
    from selfos.knowledge.changes import compare_changes
    return compare_changes(before,after,before_ledger or {},after_ledger or {},as_of=kwargs.pop('as_of',NOW),
                           operation=kwargs.pop('operation','import'),**kwargs)


def test_added_claim_retains_snapshot_and_sources():
    changes=compare({},state(record()))
    assert len(changes)==1 and changes[0]['action']=='added'
    assert changes[0]['category']=='preferences'
    assert changes[0]['before']==[] and changes[0]['after'][0]['record']['value']=='concise'
    assert changes[0]['source_ids']==['m1']


def test_claim_equality_pairs_replaced_support_without_guessing_text():
    a=record();b=record(source='m2')
    changes=compare(state(a),state(b))
    assert len(changes)==1 and changes[0]['action']=='updated'
    assert changes[0]['reason']=='support_changed'


def test_scopes_are_separate_even_with_shared_sources():
    a=record();b={**a,'scope_type':'project','scope':'synthetic-project'}
    changes=compare(state(a),state(b))
    assert sorted(c['action'] for c in changes)==['added','removed']


def test_duplicate_versions_are_a_multiset():
    a=record()
    changes=compare(state(a,copy.deepcopy(a)),state(a))
    assert len(changes)==1 and changes[0]['action']=='removed'
    assert len(changes[0]['before'])==1


def test_ambiguous_lesson_grouping_never_invents_a_merge():
    lessons=[{'text':text,'kind':'inference','domain':'work','source_ids':['m1']} for text in ('Keep originals','Keep backups')]
    changes=compare({'lessons':lessons},{'lessons':[{'text':'Use recoverable evidence','kind':'inference','domain':'work','source_ids':['m1']}]})
    assert sorted(c['action'] for c in changes)==['added','removed','removed']
    assert all(c.get('matching_reason')=='ambiguous_lineage' for c in changes)


def test_manual_edit_is_linked_by_action_originals():
    data=state(record())
    ledger=action(data,{},patch={'value':'balanced','text':'Balanced explanations'})
    changes=compare(data,data,{},ledger,operation='correction')
    assert len(changes)==1 and changes[0]['action']=='updated'
    assert changes[0]['reason']=='user_edited'
    assert changes[0]['after'][0]['record']['manual_correction']['action_id']==ledger['actions'][0]['id']


def test_user_merge_counts_one_event_with_two_originals():
    data=state(record(),record('brief','m2'))
    ledger=action(data,{},'merge',records=data['preferences'],patch={'value':'balanced','text':'Balanced explanations'})
    changes=compare(data,data,{},ledger,operation='correction')
    assert len(changes)==1 and changes[0]['action']=='merged'
    assert len(changes[0]['before'])==2 and len(changes[0]['after'])==1


def test_user_undo_restores_originals_without_editing_history():
    data=state(record(),record('brief','m2'))
    ledger=action(data,{},'merge',records=data['preferences'],patch={'value':'balanced','text':'Balanced explanations'})
    undone=create_action(data,ledger,{'action':'undo','action_id':ledger['actions'][0]['id']})
    changes=compare(data,data,ledger,undone,operation='undo')
    assert len(changes)==1 and changes[0]['action']=='restored'
    assert len(changes[0]['before'])==1 and len(changes[0]['after'])==2


def test_user_deletion_is_removal_not_a_claim_of_falsehood():
    data=state(record())
    ledger=action(data,{},'delete')
    changes=compare(data,data,{},ledger,operation='correction')
    assert len(changes)==1 and changes[0]['action']=='removed' and changes[0]['reason']=='user_deleted'


def test_facts_do_not_use_newer_dates_to_invent_replacement():
    a={**record('2020'),'key':'graduation.year'}
    b={**record('2022','m2'),'key':'graduation.year','observed_at':'2026-11-14T00:00:00Z'}
    changes=compare({'personal_facts':[a]},{'personal_facts':[b]})
    assert sorted(c['action'] for c in changes)==['added','removed']


def test_explicit_invalidated_history_keeps_reason_and_lineage():
    a=record()
    old={**a,'original_category':'preferences','status':'invalidated','invalidated_reason':'Explicitly withdrawn',
         'validity_source_ids':['m2'],'validity_evidence':'I no longer want this setting.'}
    changes=compare(state(a),{'history':[old]})
    assert len(changes)==1 and changes[0]['action']=='invalidated'
    assert changes[0]['reason']=='Explicitly withdrawn'


def test_project_aliases_and_storage_bookkeeping_do_not_fabricate_changes():
    a={'project_id':'old','title':'Synthetic project','intent':'Reliable knowledge','domain':'work','status':'in_progress',
       'source_ids':['m1'],'decisions':[],'blockers':[],'next_steps':[]}
    b={**a,'project_id':'new','_order':['later',2]}
    assert compare({'cards':{'old':a}},{'cards':{'new':b},'project_aliases':{'old':'new'}})==[]


def test_contradiction_flags_are_independent_of_primary_action():
    a=record();b={**record('detailed','m2'),'conflict':True,'conflict_source_ids':['m1','m2']}
    changes=compare(state(a),state(a,b))
    assert len(changes)==1 and changes[0]['action']=='added' and changes[0]['conflict']


def test_fixed_time_projection_preserves_scheduled_preferences():
    from selfos.knowledge.corrections import apply_corrections
    data=state(record())
    assert apply_corrections(data,{},as_of=NOW)['preferences'][0]['value']=='concise'
    assert data==state(record())


def test_comparison_deterministic_and_does_not_mutate_inputs():
    a=state(record());b=state(record(),record('detailed','m2'))
    original=copy.deepcopy((a,b))
    first=compare(a,b)
    assert first==compare(a,b)
    assert (a,b)==original
