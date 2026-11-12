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
