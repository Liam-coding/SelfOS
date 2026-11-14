"""Whole-branch review regressions, synthetic sources only."""
import base64
import copy
import io
import json
import sqlite3
import pytest
from tests.test_opencode_database import create_database
from tests.test_opencode_pipeline import summary
from tests.test_knowledge_service import refine
from selfos.sources.selection import save_sources
from selfos.app.knowledge import run_knowledge
from selfos.app.harness_imports import prepare_native, organize_native


def setup(tmp_path, count=1):
    path, selection, _ = create_database(tmp_path, count=count)
    vault = tmp_path/'vault'
    vault.mkdir()
    save_sources(vault, selection)
    return vault, path, selection


def test_rebuild_retains_completed_native_knowledge(tmp_path, monkeypatch):
    from selfos.app import knowledge
    vault, _, _ = setup(tmp_path)
    monkeypatch.setattr(knowledge,'extract_conversations',lambda *a,**k:[])
    assert run_knowledge(vault,summarize=summary,refine=refine)['installed']
    before=json.loads((vault/'.knowledge_pipeline.json').read_text())
    result=run_knowledge(vault,rebuild=True,summarize=summary,refine=refine)
    assert result['installed'],result
    after=json.loads((vault/'.knowledge_pipeline.json').read_text())
    assert set(after['sources']) == set(before['sources'])
    assert set(after['cards']) == set(before['cards'])


def test_real_ingestion_merges_selected_database_copies(tmp_path,monkeypatch):
    from selfos.app import knowledge
    vault,path,selection=setup(tmp_path)
    alternate=tmp_path/'alternate.db'
    alternate.write_bytes(path.read_bytes())
    selection['entries'].append({'kind':'opencode_database','path':str(alternate)})
    save_sources(vault,selection)
    monkeypatch.setattr(knowledge,'extract_conversations',lambda *a,**k:[])
    result=run_knowledge(vault,summarize=summary,refine=refine)
    assert result['installed'],result
    state=json.loads((vault/'.knowledge_pipeline.json').read_text())
    assert len(next(iter(state['sources'].values()))['source_locators'])==2


def test_project_alias_keeps_native_source_identity_and_preview_receipts(tmp_path):
    from selfos.app.pipeline import register_project_aliases
    from selfos.app.library import knowledge_source
    vault,_,selection=setup(tmp_path)
    preview=prepare_native(vault,selection['entries'][0])
    assert organize_native(vault,preview['id'],summarize=summary,refine=refine)['installed']
    state=json.loads((vault/'.knowledge_pipeline.json').read_text())
    original=next(iter(state['cards']))
    register_project_aliases(vault,{original:'canonical-synthetic-project'})
    assert knowledge_source(vault,next(iter(state['sources'])))['text']
    # A fresh retained preview uses alias-aware receipt keys on publication.
    from selfos.storage.harness_scans import restart_scan
    restart_scan(vault,selection['entries'][0],max_chars=preview['part_chars'])
    preview=prepare_native(vault,selection['entries'][0])
    result=organize_native(vault,preview['id'],summarize=summary,refine=refine)
    assert result['status']=='completed',result


@pytest.mark.parametrize('selected',[False,True])
def test_unselected_consumed_record_changes_block_publication(tmp_path,monkeypatch,selected):
    from selfos.app import knowledge
    vault,path,selection=setup(tmp_path,count=8)
    with sqlite3.connect(path) as db:
        for index in range(8):
            db.execute('UPDATE part SET data=? WHERE id=?',(json.dumps({'type':'text','text':
                'We are designing synthetic verified recoverable knowledge. '*150}),f'prt_{index:04d}_a'))
    db.close()
    monkeypatch.setattr(knowledge,'extract_conversations',lambda *a,**k:[])
    preview=prepare_native(vault,selection['entries'][0])
    chosen={message['native_message_id'] for session in preview['sessions'] for message in session['messages']}
    omitted=next(f'msg_{index:04d}' for index in range(8) if f'msg_{index:04d}' not in chosen)
    def changing(session):
        result=summary(session)
        with sqlite3.connect(path) as db:
            db.execute('UPDATE part SET data=? WHERE id=?',(json.dumps({'type':'text','text':'New durable unselected decision.'}),omitted.replace('msg_','prt_')+'_a'))
        db.close()
        return result
    if selected:
        result=organize_native(vault,preview['id'],summarize=changing,refine=refine)
    else:result=run_knowledge(vault,summarize=changing,refine=refine)
    assert not result['installed'],result
    assert not (vault/'.knowledge_pipeline.json').exists()


@pytest.mark.parametrize('selected',[False,True])
def test_acknowledgement_failure_preserves_installed_result(tmp_path,monkeypatch,selected):
    from selfos.app import knowledge,harness_imports
    from selfos.storage import harness_scans
    vault,_,selection=setup(tmp_path)
    monkeypatch.setattr(knowledge,'extract_conversations',lambda *a,**k:[])
    def broken(*a,**k):raise OSError('Synthetic checkpoint write failed')
    monkeypatch.setattr(harness_scans,'acknowledge_scan',broken)
    monkeypatch.setattr(harness_imports,'acknowledge_scan',broken)
    if selected:
        preview=prepare_native(vault,selection['entries'][0])
        result=organize_native(vault,preview['id'],summarize=summary,refine=refine)
    else:result=run_knowledge(vault,summarize=summary,refine=refine)
    assert result['installed'] and result['status']=='completed' and result['operation_id'],result
    assert result['native_acknowledgement_pending']


@pytest.mark.parametrize('field,value',[('timestamp','2025-01-01T00:00:00Z'),('role','assistant'),
    ('project_id','forged-project'),('cwd','/synthetic/forged')])
def test_migration_rejects_semantic_source_forgery(tmp_path,field,value):
    from tests.test_opencode_export import export_wire
    from selfos.sources.upload_admission import admit_document
    from selfos.app.uploads import upload_preview,organize_uploads
    from selfos.app.migration import export_package,import_package
    vault=tmp_path/'vault';vault.mkdir()
    raw=json.dumps(export_wire(tmp_path)).encode()
    doc=admit_document(vault,'session.json',io.BytesIO(raw),len(raw))['document']
    preview=upload_preview(vault,[doc['id']])
    assert organize_uploads(vault,preview['id'],summarize=summary,refine=refine)['installed']
    package=export_package(vault,tmp_path,include_originals=True)
    state=json.loads(base64.b64decode(package['files']['.knowledge_pipeline.json']))
    next(iter(state['sources'].values()))[field]=value
    package['files']['.knowledge_pipeline.json']=base64.b64encode(json.dumps(state).encode()).decode()
    with pytest.raises(ValueError):import_package(tmp_path/'destination',tmp_path/'root',package)


def test_equivalent_export_copies_keep_both_document_completion_bindings(tmp_path):
    from tests.test_opencode_export import export_wire
    from selfos.sources.upload_admission import admit_document
    from selfos.app.uploads import upload_preview,organize_uploads
    from selfos.app.migration import export_package,import_package
    vault=tmp_path/'vault';vault.mkdir()
    wire=export_wire(tmp_path)
    documents=[]
    for number,indent in enumerate((None,2)):
        raw=json.dumps(wire,indent=indent).encode()
        documents.append(admit_document(vault,f'copy{number}.json',io.BytesIO(raw),len(raw))['document']['id'])
    assert len(set(documents))==2
    preview=upload_preview(vault,documents)
    assert organize_uploads(vault,preview['id'],summarize=summary,refine=refine)['installed']
    assert not upload_preview(vault,documents)['sessions']
    package=export_package(vault,tmp_path,include_originals=True)
    import_package(tmp_path/'destination',tmp_path/'root',package)


def test_foreign_descriptive_project_path_never_probes_host_directory(monkeypatch):
    import os
    from pathlib import Path
    from selfos.sources.compaction import canonical_project
    foreign='/synthetic/foreign-project' if os.name=='nt' else 'C:/synthetic/foreign-project'
    canonical_project.cache_clear()
    def forbidden(*args):raise AssertionError('Foreign descriptive paths are not host IO targets')
    monkeypatch.setattr(Path,'is_dir',forbidden)
    assert canonical_project(foreign)==foreign
