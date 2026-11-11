import selfos.app.pipeline as _app_pipeline
import json

from tests.test_project_knowledge_contract import session,summary


def sessions(tmp_path):
    return [session('First project uses replay-safe ingestion.',identity='m1',session='s1',project=str(tmp_path/'repo-a')),
            session('Second project uses replay-safe ingestion.',identity='m2',session='s2',project=str(tmp_path/'repo-b'))]


def extract(item,domain='work'):
    result=summary(item)
    result['lessons']=[{'text':'Preserve replay safety through idempotent processing.',
                       'source_ids':[item['messages'][0]['id']],'kind':'inference','domain':domain}]
    return result


def test_equal_text_does_not_merge_explicitly_different_domains(tmp_path):
    items=sessions(tmp_path);vault=tmp_path/'vault'
    _app_pipeline.consolidate_sessions(vault,items,lambda item:extract(item,'work' if item['session_id']=='s1' else 'research'))
    state=json.loads((vault/'.knowledge_pipeline.json').read_text())
    assert len(state['lessons'])==2
    assert {(row['domain'],tuple(row['source_ids'])) for row in state['lessons']}=={('work',('m1',)),('research',('m2',))}


def test_stopping_after_one_project_refinement_preserves_other_project_sources(tmp_path):
    items=sessions(tmp_path);vault=tmp_path/'vault'
    _app_pipeline.consolidate_sessions(vault,items,extract,max_workers=1)
    stop=False
    def refine(payload):
        nonlocal stop
        stop=True
        return {'project':payload['project'],'lessons':[],'observations':[]}
    result=_app_pipeline.refine_projects(vault,refine,cancel=lambda:stop)
    state=json.loads((vault/'.knowledge_pipeline.json').read_text())
    assert result['projects']==1
    assert len(state['lessons'])==1
    assert state['lessons'][0]['source_ids']==['m2']
    assert state['lessons'][0]['domain']=='work'
    assert state['cards'][items[1]['project_id']]['source_ids']==['m2']
    assert items[1]['project_id'] not in state['refined']
