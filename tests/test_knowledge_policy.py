from selfos.storage.settings import save_settings
from selfos.storage.settings import load_settings
from selfos.knowledge.settings import DEFAULT_SETTINGS
from selfos.knowledge.records import merge_records
from selfos.knowledge.records import validate_record
from selfos.storage.records import record_writes
import copy,json
import pytest
from pathlib import Path
import importlib
from tests.test_project_knowledge_contract import session

def record(value='Chinese', key='communication.language', **changes):
    return dict(key=key,value=value,text='Prefers '+value,domain='personal',kind='user_fact',
                source_ids=['m1'],evidence='I prefer Chinese explanations.',**changes)

def evidence():
    return session('I prefer Chinese explanations.')

def test_settings_are_vault_specific_and_not_person_specific(tmp_path):
    a,b=tmp_path/'alice',tmp_path/'bob'
    save_settings(a,{'domains':['research','music'],'detail':'detailed'})
    assert load_settings(a)['domains']==['research','music']
    assert load_settings(b)['detail']=='balanced'
    assert 'I748319' not in json.dumps(load_settings(b))

@pytest.mark.parametrize('bad',[
 {'domains':[],'detail':'balanced'},{'domains':['work'],'detail':'maximum'},
 {'domains':'work','detail':'balanced'},{'domains':['../work'],'detail':'balanced'},
 {'domains':['work'],'detail':'balanced','api_key':'secret'}])
def test_bad_settings_are_rejected_without_overwriting(tmp_path,bad):
    save_settings(tmp_path,{'domains':['work'],'detail':'concise'})
    original=(tmp_path/'.knowledge_settings.json').read_bytes()
    with pytest.raises(ValueError):save_settings(tmp_path,bad)
    assert (tmp_path/'.knowledge_settings.json').read_bytes()==original

def test_only_explicit_sourced_quotes_enter_personal_facts():
    r=record()
    assert validate_record(r,evidence())['kind']=='user_fact'
    with pytest.raises(ValueError):validate_record({**r,'evidence':'I never said this'},evidence())
    quoted=evidence();quoted['messages'][0]['provenance']='quoted_dialogue'
    assert validate_record(r,quoted)['kind']=='inference'

def test_focus_policy_excludes_unselected_domains_but_records_reason():
    state={}
    merge_records(state,'personal_facts',[validate_record(record(),evidence())],
                    {'domains':['research'],'detail':'balanced'})
    assert not state['personal_facts']
    assert state['retention_audit'][-1]['reason']=='outside_selected_domains'

def test_unique_facts_are_not_reduced_to_a_target_count():
    state={}
    records=[]
    for i in range(60):
        quote=f'I maintain project number {i}.'
        raw=record(value=str(i),key=f'project.{i}')
        raw.update(text=quote,evidence=quote)
        records.append(validate_record(raw,session(quote)))
    merge_records(state,'personal_facts',records,DEFAULT_SETTINGS)
    assert len(state['personal_facts'])==60

def test_preference_changes_keep_the_old_choice_in_history():
    state={}
    old=validate_record(record(),evidence())
    raw=record(value='English');raw['evidence']='I prefer English explanations.'
    src=session(raw['evidence']);src['messages'][0]['timestamp']='2026-11-11T08:00:00Z'
    newer=validate_record(raw,src)
    merge_records(state,'preferences',[old,newer],DEFAULT_SETTINGS)
    assert state['preferences'][0]['value']=='English'
    assert any(r['value']=='Chinese' for r in state['records_history'])


def test_repeated_preference_uses_the_latest_evidence_date():
    state={};records=[]
    for day,value in [(10,'Chinese'),(12,'Chinese'),(11,'English')]:
        raw=record(value=value);raw['evidence']=f'I prefer {value} explanations.'
        src=session(raw['evidence']);src['messages'][0]['timestamp']=f'2026-11-{day}T08:00:00Z'
        records.append(validate_record(raw,src))
    merge_records(state,'preferences',records,DEFAULT_SETTINGS)
    assert state['preferences'][0]['value']=='Chinese'
    assert state['preferences'][0]['observed_at']=='2026-11-12T08:00:00Z'

def test_conflicting_facts_are_preserved_and_marked():
    state={}
    quote='I work at Example Company.'
    raw=record(value='Example Company',key='current.employer')
    raw.update(text=quote,evidence=quote)
    a=validate_record(raw,session(quote))
    quote='I work at Other Company.'
    raw.update(value='Other Company',text=quote,evidence=quote)
    b=validate_record(raw,session(quote))
    merge_records(state,'personal_facts',[a,b],DEFAULT_SETTINGS)
    assert len(state['personal_facts'])==2
    assert all(r['conflict'] for r in state['personal_facts'])

def test_managed_typed_records_do_not_erase_manual_notes(tmp_path):
    state={};merge_records(state,'preferences',[validate_record(record(),evidence())],DEFAULT_SETTINGS)
    path=tmp_path/'knowledge/preferences.md';path.parent.mkdir();path.write_text('Manual note: check tone.\n')
    writes=record_writes(tmp_path,state)
    text=writes['knowledge/preferences.md'].decode()
    assert 'Manual note: check tone.' in text and 'Prefers Chinese' in text
