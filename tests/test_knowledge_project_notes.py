import selfos.app.pipeline as _app_pipeline
import selfos.storage.pipeline as _storage_pipeline
import selfos.storage.documents as _storage_documents
import json
import pytest

from tests.test_project_knowledge_contract import session,summary


def project_file(vault):
    return next((vault/'02_Work/projects').glob('*.md'))


@pytest.mark.parametrize('legacy',[False,True])
def test_incremental_project_update_preserves_manual_notes(tmp_path,legacy):
    _app_pipeline.consolidate_sessions(tmp_path,[session()],summary)
    path=project_file(tmp_path)
    if legacy:
        state=json.loads((tmp_path/'.knowledge_pipeline.json').read_text())
        path.write_bytes(_storage_documents.render_card(next(iter(state['cards'].values()))))
    path.write_bytes(path.read_bytes()+b'\n## My notes\nKeep this manual rationale.\n')
    _app_pipeline.consolidate_sessions(tmp_path,[session(identity='m2',session='s2',timestamp='2026-11-11T09:00:00Z')],
                           lambda item:summary(item,next_steps=['Measure latency']))
    text=path.read_text()
    assert 'Keep this manual rationale.' in text and 'Measure latency' in text
    assert text.count('Keep this manual rationale.')==1


def test_project_refinement_preserves_manual_notes(tmp_path):
    _app_pipeline.consolidate_sessions(tmp_path,[session()],summary)
    path=project_file(tmp_path);path.write_bytes(path.read_bytes()+b'\nMy personal design note.\n')
    _app_pipeline.refine_projects(tmp_path,lambda payload:{'project':payload['project'],'lessons':[]})
    assert 'My personal design note.' in path.read_text()


@pytest.mark.parametrize('keep_project',[True,False])
def test_rebuild_keeps_notes_and_backup_restores_exact_file(tmp_path,keep_project):
    vault=tmp_path/'vault';scratch=tmp_path/'scratch'
    _app_pipeline.consolidate_sessions(vault,[session()],summary)
    path=project_file(vault);path.write_bytes(path.read_bytes()+b'\n## Manual notes\nKeep local design choices.\n')
    before=path.read_bytes()
    _app_pipeline.consolidate_sessions(scratch,[session()],summary)
    state_path=scratch/'.knowledge_pipeline.json';state=json.loads(state_path.read_text())
    state['quality_version']=2
    if not keep_project:state['cards']={}
    state_path.write_text(json.dumps(state))
    result=_app_pipeline.install_rebuilt(vault,scratch)
    assert path.exists() and 'Keep local design choices.' in path.read_text()
    if not keep_project:assert 'Project summary' not in path.read_text()
    _storage_pipeline.restore_pipeline_backup(vault,result)
    assert path.read_bytes()==before
