import json
from pathlib import Path
import knowledge_pipeline as p
from tests.test_project_knowledge_contract import session,summary

def typed(item):
    return {'project':None,'lessons':[],
        'personal_facts':[{'key':'employment.employer','value':'SAP','text':'Works at SAP','domain':'work',
                          'kind':'user_fact','source_ids':['m1'],'evidence':'I work at SAP.'}],
        'preferences':[{'key':'communication.language','value':'Chinese','text':'Prefers Chinese','domain':'personal',
                        'kind':'user_fact','source_ids':['m1'],'evidence':'I prefer Chinese.'}]}

def test_typed_records_are_saved_separately_with_sources(tmp_path):
    p.consolidate_sessions(tmp_path,[session('I work at SAP. I prefer Chinese.')],typed)
    assert 'Works at SAP' in (tmp_path/'knowledge/personal_facts.md').read_text()
    assert 'Prefers Chinese' in (tmp_path/'knowledge/preferences.md').read_text()
    assert 'm1' in (tmp_path/'knowledge/personal_facts.md').read_text()
    assert not list((tmp_path/'02_Work/projects').glob('*.md'))

def test_domain_selection_applies_to_projects_and_lessons(tmp_path):
    def unrelated(item):
        candidate=summary(item);candidate['project']['domain']='work'
        candidate['lessons']=[{'text':'Use bounded retries','kind':'inference','domain':'work','source_ids':['m1']}]
        return candidate
    p.consolidate_sessions(tmp_path,[session()],unrelated,settings={'domains':['research'],'detail':'balanced'})
    state=json.loads((tmp_path/'.knowledge_pipeline.json').read_text())
    assert state['cards']=={} and state['lessons']==[]
    assert state['retention_audit']

def test_detail_changes_current_view_without_discarding_history(tmp_path):
    def many(item):return summary(item,decisions=[f'Useful decision {i}' for i in range(10)])
    p.consolidate_sessions(tmp_path,[session()],many,settings={'domains':['work'],'detail':'detailed'})
    state=json.loads((tmp_path/'.knowledge_pipeline.json').read_text())
    assert len(next(iter(state['cards'].values()))['decisions'])==10
    assert len(next(iter(state['cards'].values()))['decision_history'])==10
