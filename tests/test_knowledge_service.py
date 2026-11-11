import importlib,json,copy
from pathlib import Path
import pytest
from selfos.storage.settings import save_settings
from tests.test_project_knowledge_contract import card

def api():
    try:return importlib.import_module('selfos.app.knowledge')
    except ModuleNotFoundError:pytest.fail('knowledge_service not implemented')

def source(tmp_path):
    root=tmp_path/'sessions';root.mkdir()
    rows=[{'type':'session_meta','payload':{'id':'original','cwd':'C:/projects/alpha'}},
          {'type':'response_item','timestamp':'2026-11-10T08:00:00Z','payload':{'type':'message','role':'user',
           'content':[{'type':'input_text','text':'I prefer Chinese. We are building reliable import.'}]}}]
    path=root/'source.jsonl';path.write_text('\n'.join(json.dumps(r) for r in rows))
    return root,path

def summarize(item):
    m=item['messages'][0]
    project=card(project_id=item['project_id'],source_ids=[m['id']],updated_at=m['timestamp'],domain='work')
    return {'project':project,'lessons':[], 'preferences':[{'key':'language','value':'Chinese','text':'Prefers Chinese',
        'source_ids':[m['id']],'kind':'user_fact','evidence':'I prefer Chinese.','domain':'personal'}]}

def refine(payload):return {'project':copy.deepcopy(payload['project']),'lessons':payload['lessons']}

def test_first_import_then_cached_import_has_no_extra_model_calls(tmp_path):
    s=api();roots,path=source(tmp_path);vault=tmp_path/'vault'
    s.run_knowledge(vault,roots=[roots],summarize=summarize,refine=refine)
    result=s.run_knowledge(vault,roots=[roots],summarize=lambda _:pytest.fail('cached'),refine=lambda _:pytest.fail('cached'))
    assert result['model_calls']==0 and result['status']=='completed'

def test_changed_policy_rebuilds_automatically_and_preserves_raw_source(tmp_path):
    s=api();roots,path=source(tmp_path);raw=path.read_bytes();vault=tmp_path/'vault'
    s.run_knowledge(vault,roots=[roots],summarize=summarize,refine=refine)
    save_settings(vault,{'domains':['personal'],'detail':'concise'})
    result=s.run_knowledge(vault,roots=[roots],summarize=summarize,refine=refine)
    assert result['mode']=='rebuild' and result['installed']
    state=json.loads((vault/'.knowledge_pipeline.json').read_text())
    assert not state['cards'] and state['preferences']
    assert path.read_bytes()==raw

def test_failed_rebuild_does_not_replace_the_previous_knowledge(tmp_path):
    s=api();roots,_=source(tmp_path);vault=tmp_path/'vault'
    s.run_knowledge(vault,roots=[roots],summarize=summarize,refine=refine)
    old=(vault/'.knowledge_pipeline.json').read_bytes()
    def fail(_):raise ValueError('invalid model output')
    result=s.run_knowledge(vault,roots=[roots],summarize=fail,refine=refine,rebuild=True)
    assert result['status']=='failed' and not result['installed']
    assert (vault/'.knowledge_pipeline.json').read_bytes()==old

def test_cancelled_rebuild_keeps_the_previous_knowledge(tmp_path):
    s=api();roots,_=source(tmp_path);vault=tmp_path/'vault'
    s.run_knowledge(vault,roots=[roots],summarize=summarize,refine=refine)
    old=(vault/'.knowledge_pipeline.json').read_bytes()
    result=s.run_knowledge(vault,roots=[roots],summarize=summarize,refine=refine,rebuild=True,cancel=lambda:True)
    assert result['status']=='stopped' and (vault/'.knowledge_pipeline.json').read_bytes()==old

def test_one_click_undo_restores_all_stages_of_an_import(tmp_path):
    s=api();roots,_=source(tmp_path);vault=tmp_path/'vault'
    result=s.run_knowledge(vault,roots=[roots],summarize=summarize,refine=refine)
    assert (vault/'knowledge/preferences.md').exists()
    s.restore_last(vault,result['operation_id'])
    assert not (vault/'.knowledge_pipeline.json').exists()
    assert not list((vault/'02_Work/projects').glob('*.md'))

def test_undo_refuses_modified_files_before_restoring_anything(tmp_path):
    s=api();roots,_=source(tmp_path);vault=tmp_path/'vault'
    result=s.run_knowledge(vault,roots=[roots],summarize=summarize,refine=refine)
    state=(vault/'.knowledge_pipeline.json').read_bytes()
    (vault/'knowledge/preferences.md').write_text('Manually edited')
    with pytest.raises(ValueError):s.restore_last(vault,result['operation_id'])
    assert (vault/'.knowledge_pipeline.json').read_bytes()==state


def test_failed_import_reuses_successful_staged_sessions_on_retry(tmp_path):
    s=api();roots,path=source(tmp_path);vault=tmp_path/'vault'
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    rows[0]['payload'].update(id='second',cwd='C:/projects/beta')
    rows[1]['payload']['content'][0]['text']+=' Beta work.'
    (roots/'second.jsonl').write_text('\n'.join(json.dumps(row) for row in rows))
    successful=[]
    def first(item):
        if item['session_id']=='second': raise ValueError('temporary failure')
        successful.append(item['session_id']);return summarize(item)
    result=s.run_knowledge(vault,roots=[roots],summarize=first,refine=refine)
    assert result['status']=='failed' and not (vault/'.knowledge_pipeline.json').exists()
    def retry(item):
        assert item['session_id'] not in successful
        return summarize(item)
    assert s.run_knowledge(vault,roots=[roots],summarize=retry,refine=refine)['installed']


def test_new_conversation_does_not_invalidate_other_successful_checkpoints(tmp_path):
    s=api();roots,path=source(tmp_path);vault=tmp_path/'vault'
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    rows[0]['payload'].update(id='second',cwd='C:/projects/beta')
    rows[1]['payload']['content'][0]['text']+=' Beta work.'
    (roots/'second.jsonl').write_text('\n'.join(json.dumps(row) for row in rows))
    def first(item):
        if item['session_id']=='second':raise ValueError('temporary failure')
        return summarize(item)
    assert s.run_knowledge(vault,roots=[roots],summarize=first,refine=refine)['status']=='failed'
    rows[0]['payload'].update(id='third',cwd='C:/projects/gamma')
    rows[1]['payload']['content'][0]['text']+=' Gamma work.'
    (roots/'third.jsonl').write_text('\n'.join(json.dumps(row) for row in rows))
    calls=[]
    def retry(item):calls.append(item['session_id']);return summarize(item)
    result=s.run_knowledge(vault,roots=[roots],summarize=retry,refine=refine)
    assert result['installed'] and set(calls)=={'second','third'},result
