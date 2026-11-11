import selfos.app.pipeline as _app_pipeline
import copy,json
import pytest

from selfos.app.library import list_knowledge, knowledge_detail
from tests.test_project_knowledge_contract import session,summary


def test_project_observation_is_stored_separately_and_has_sources(tmp_path):
    _app_pipeline.consolidate_sessions(tmp_path,[session()],summary)
    def refine(payload):
        return {'project':payload['project'],'lessons':[], 'observations':[
            {'text':'Experiment A used a 0.15 score gap on this dataset.',
             'source_ids':['m1'],'kind':'inference','domain':'work'}]}
    _app_pipeline.refine_projects(tmp_path,refine)
    state=json.loads((tmp_path/'.knowledge_pipeline.json').read_text())
    assert not state['lessons']
    assert state['project_observations'][0]['source_ids']==['m1']
    assert state['project_observations'][0]['source_scope']=='summary_context'
    row=list_knowledge(tmp_path,'history',query='0.15')['items'][0]
    assert knowledge_detail(tmp_path,row['id'])['item']['source_scope']=='summary_context'
    assert '0.15' in (tmp_path/'knowledge/history.md').read_text()
    assert '0.15' not in (tmp_path/'05_Life/lessons.md').read_text()


def test_untraceable_observation_does_not_change_knowledge(tmp_path):
    _app_pipeline.consolidate_sessions(tmp_path,[session()],summary)
    path=tmp_path/'.knowledge_pipeline.json';previous=path.read_bytes()
    def refine(payload):
        return {'project':payload['project'],'lessons':[], 'observations':[
            {'text':'Unsupported observation','source_ids':['invented'],'kind':'inference','domain':'work'}]}
    with pytest.raises(ValueError,match='untraceable'):_app_pipeline.refine_projects(tmp_path,refine)
    assert path.read_bytes()==previous


def test_old_lesson_candidates_stay_internal_instead_of_polluting_history(tmp_path):
    def extract(item):
        result=summary(item)
        result['lessons']=[{'text':'Temporary rerun command','source_ids':['m1'],'kind':'inference','domain':'work'}]
        return result
    _app_pipeline.consolidate_sessions(tmp_path,[session()],extract)
    _app_pipeline.refine_projects(tmp_path,lambda payload:{'project':payload['project'],'lessons':[],'observations':[]})
    state=json.loads((tmp_path/'.knowledge_pipeline.json').read_text())
    assert state['lesson_history'][0]['text']=='Temporary rerun command'
    from selfos.storage.records import record_writes
    assert b'Temporary rerun command' not in record_writes(tmp_path,state)['knowledge/history.md']


def test_synthesis_cannot_bypass_selected_domains(tmp_path):
    _app_pipeline.consolidate_sessions(tmp_path,[session()],summary,settings={'domains':['work'],'detail':'balanced'})
    def refine(payload):
        record={'text':'An unrelated health claim','source_ids':['m1'],'kind':'inference','domain':'health'}
        return {'project':payload['project'],'lessons':[record],'observations':[record]}
    _app_pipeline.refine_projects(tmp_path,refine)
    state=json.loads((tmp_path/'.knowledge_pipeline.json').read_text())
    assert not state['lessons'] and not state['project_observations']
    assert any(r['category']=='project_observation' for r in state['retention_audit'])


def test_repaired_review_has_a_persisted_redacted_diagnostic(tmp_path):
    _app_pipeline.consolidate_sessions(tmp_path,[session()],summary)
    def refine(payload):
        return {'project':payload['project'],'lessons':[], 'observations':[],
                '_lesson_review_errors':[{'batch_start':20,'attempt':1,'error':'Missing candidate',
                                         'raw_response':'Invalid verdict response'}]}
    progress=[]
    _app_pipeline.refine_projects(tmp_path,refine,progress=progress.append)
    paths=list((tmp_path/'.knowledge_errors').rglob('*.json'))
    assert len(paths)==1
    diagnostic=json.loads(paths[0].read_text())
    assert diagnostic['error']=='Missing candidate'
    assert diagnostic['response_redacted']=='Invalid verdict response'
    assert diagnostic['known_source_ids']==['m1']
    assert any(line.startswith('Diagnostic:') for line in progress)


def test_failed_project_synthesis_has_diagnostics_and_preserves_state(tmp_path):
    from selfos.knowledge.contracts import ResponseFormatError
    _app_pipeline.consolidate_sessions(tmp_path,[session()],summary)
    previous=(tmp_path/'.knowledge_pipeline.json').read_bytes()
    def refine(payload):raise ResponseFormatError('Invalid merge','Bad model output')
    with pytest.raises(ResponseFormatError):_app_pipeline.refine_projects(tmp_path,refine)
    assert (tmp_path/'.knowledge_pipeline.json').read_bytes()==previous
    paths=list((tmp_path/'.knowledge_errors').rglob('*.json'))
    assert len(paths)==3
    assert all(json.loads(path.read_text())['response_redacted']=='Bad model output' for path in paths)
