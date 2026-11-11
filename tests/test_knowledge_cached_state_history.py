import selfos.storage.files as _storage_files
import selfos.storage.pipeline as _storage_pipeline
import copy,json
from selfos.app.pipeline import consolidate_sessions
from selfos.storage.pipeline import restore_pipeline_backup
from selfos.knowledge.history import history_records
from tests.test_project_knowledge_contract import session,card


def legacy_checkpoint(vault):
    sessions=[session('Project blocked on source mapping.',identity='m1',session='s1'),
              session('Mapping fixed; validate retries.',identity='m2',session='s2',timestamp='2026-11-10T09:00:00Z')]
    def extract(item):
        blocked=item['session_id']=='s1'
        return {'project':card(project_id=item['project_id'],source_ids=[item['messages'][0]['id']],
            status='blocked' if blocked else 'in_progress',blockers=['Missing mapping'] if blocked else [],
            next_steps=['Repair mapping'] if blocked else ['Validate retries']), 'lessons':[]}
    consolidate_sessions(vault,sessions,extract)
    path=vault/'.knowledge_pipeline.json'
    state=json.loads(path.read_text())
    for project in state['cards'].values():
        project.pop('state_inputs',None);project.pop('state_records',None)
    path.write_text(json.dumps(state),encoding='utf-8')
    return sessions,state


def no_model(_):raise AssertionError('Cached upgrade must not call the model')


def test_cached_only_run_rebuilds_history_with_backup_and_exact_restore(tmp_path):
    sessions,old=legacy_checkpoint(tmp_path)
    path=tmp_path/'.knowledge_pipeline.json';before=path.read_bytes()
    result=consolidate_sessions(tmp_path,sessions,no_model)
    assert result['model_calls']==0 and result['completed_sessions']==0
    assert result['history_upgraded']==1 and result['run_id']
    current=json.loads(path.read_text())
    project=next(iter(current['cards'].values()))
    assert project['status']=='in_progress' and project['blockers']==[]
    historical=[r for r in history_records(current) if r.get('original_category')=='project_state']
    assert len(historical)==1 and historical[0]['source_ids']==['m1']
    assert historical[0]['source_scope']=='session_context'
    assert current['cache']==old['cache'] and current['summaries']==old['summaries']
    again=consolidate_sessions(tmp_path,sessions,no_model)
    assert again['history_upgraded']==0 and again['run_id'] is None
    restore_pipeline_backup(tmp_path,result['run_id'])
    assert path.read_bytes()==before


def test_cancelled_upgrade_preserves_exact_checkpoint(tmp_path):
    sessions,_=legacy_checkpoint(tmp_path)
    path=tmp_path/'.knowledge_pipeline.json';before=path.read_bytes()
    result=consolidate_sessions(tmp_path,sessions,no_model,cancel=lambda:True)
    assert result['history_upgraded']==0 and result['model_calls']==0
    assert path.read_bytes()==before


def test_history_rebuild_rejects_foreign_sources_and_selected_domain_mismatch():
    from selfos.knowledge.history import rebuild_cached_state_history
    project=card(decision_history=['Existing decision'])
    state={'cards':{project['project_id']:copy.deepcopy(project)},'summaries':{'bad':{'project':card(source_ids=['foreign'])}},
           'sources':{'foreign':{'project_id':'other/project','timestamp':'2026-11-10T08:00:00Z'}}}
    original=copy.deepcopy(state)
    assert rebuild_cached_state_history(state,['work'])==0
    assert state==original
    state['summaries']['bad']['project']['source_ids']=['m1']
    state['sources']['m1']={'project_id':project['project_id'],'timestamp':'2026-11-10T08:00:00Z'}
    original=copy.deepcopy(state)
    assert rebuild_cached_state_history(state,['health'])==0 and state==original


def test_cached_refinement_also_upgrades_without_resynthesis(tmp_path):
    from selfos.app.pipeline import refine_projects
    legacy_checkpoint(tmp_path)
    refine_projects(tmp_path,lambda payload:{'project':payload['project'],'lessons':[],'observations':[]})
    path=tmp_path/'.knowledge_pipeline.json';state=json.loads(path.read_text())
    for project in state['cards'].values():
        project.pop('state_inputs',None);project.pop('state_records',None)
    path.write_text(json.dumps(state),encoding='utf-8')
    result=refine_projects(tmp_path,no_model)
    assert result['projects']==0 and result['model_calls']==0
    assert result['history_upgraded']==1 and result['run_id']
    current=json.loads(path.read_text())
    assert next(iter(current['cards'].values()))['state_records'][0]['source_ids']==['m1']


def test_stop_after_local_rebuild_prevents_upgrade_write(tmp_path):
    sessions,_=legacy_checkpoint(tmp_path)
    path=tmp_path/'.knowledge_pipeline.json';before=path.read_bytes()
    checks=0
    def cancel():
        nonlocal checks
        checks+=1
        return checks>=2
    result=consolidate_sessions(tmp_path,sessions,no_model,cancel=cancel)
    assert result['history_upgraded']==0 and result['cancelled']
    assert path.read_bytes()==before


def test_failed_history_upgrade_rolls_back_both_files(tmp_path,monkeypatch):
    import pytest
    sessions,_=legacy_checkpoint(tmp_path)
    paths=[tmp_path/'.knowledge_pipeline.json',tmp_path/'knowledge/history.md']
    before={path:path.read_bytes() for path in paths}
    original=_storage_files._atomic_write
    failed=False
    def fail_history_once(path,content):
        nonlocal failed
        if path==paths[1] and not failed:
            failed=True
            raise OSError('simulated history write failure')
        return original(path,content)
    monkeypatch.setattr(_storage_files,'_atomic_write',fail_history_once)
    with pytest.raises(OSError,match='simulated'):consolidate_sessions(tmp_path,sessions,no_model)
    assert {path:path.read_bytes() for path in paths}==before
    assert not (tmp_path/'.knowledge_pending.json').exists()


def test_older_snapshots_recover_domains_without_duplicate_events():
    from selfos.knowledge.history import rebuild_cached_state_history
    from selfos.knowledge.projects import merge_project_card
    old=card(domain='work',source_ids=['m1'])
    new=card(domain='research',source_ids=['m2'],updated_at='2026-11-10T09:00:00Z')
    current=merge_project_card(old,new)
    for group in ('state_inputs','state_records'):
        for record in current[group]:record.pop('domain',None)
    state={'cards':{old['project_id']:current},'summaries':{'old':{'project':old},'new':{'project':new}},
        'sources':{'m1':{'project_id':old['project_id'],'timestamp':old['updated_at']},
                   'm2':{'project_id':new['project_id'],'timestamp':new['updated_at']}}}
    assert rebuild_cached_state_history(state,['work','research'])==1
    assert len(current['state_inputs'])==2 and len(current['state_records'])==2
    records=[r for r in history_records(state) if r.get('original_category')=='project_state']
    assert records[0]['domain']=='work' and records[0]['source_ids']==['m1']
    assert rebuild_cached_state_history(state,['work','research'])==0
