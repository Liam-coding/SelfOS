import json
import copy
import pytest

from selfos.app.corrections import correct_knowledge
from selfos.app.library import list_knowledge, knowledge_detail
from selfos.storage.corrections import load_corrections
from selfos.storage.records import record_writes
from tests.test_knowledge_corrections import record, state


def prepare(vault):
    data=state(record());data.update(cache={},cards={},lessons=[])
    (vault/'.knowledge_pipeline.json').write_text(json.dumps(data))
    return data


def edit(vault):
    row=list_knowledge(vault,category='preferences')['items'][0]
    return correct_knowledge(vault,dict(action='edit',ids=[row['id']],patch={'value':'balanced','text':'Balanced explanations'}))


def test_atomic_edit_updates_view_exports_and_keeps_generated_state(tmp_path):
    original=prepare(tmp_path)
    result=edit(tmp_path)
    assert result['action_id'] and result['backup_id']
    assert json.loads((tmp_path/'.knowledge_pipeline.json').read_text())==original
    row=list_knowledge(tmp_path,category='preferences')['items'][0]
    assert row['title']=='balanced'
    assert knowledge_detail(tmp_path,row['id'])['item']['user_corrected']
    assert 'Balanced explanations' in (tmp_path/'knowledge/preferences.md').read_text()
    assert load_corrections(tmp_path)['actions']


def test_later_generated_write_applies_the_same_durable_overlay(tmp_path):
    data=prepare(tmp_path);edit(tmp_path)
    assert 'Balanced explanations' in record_writes(tmp_path,data)['knowledge/preferences.md'].decode()
    data['preferences'].append(record('detailed','m2'))
    (tmp_path/'.knowledge_pipeline.json').write_text(json.dumps(data))
    rows=list_knowledge(tmp_path,category='preferences')['items']
    assert {r['title'] for r in rows}=={'balanced','detailed'}
    assert all(r['conflict'] for r in rows)


def test_undo_does_not_remove_new_generated_evidence(tmp_path):
    data=prepare(tmp_path);result=edit(tmp_path)
    data['preferences'].append(record('detailed','m2'))
    (tmp_path/'.knowledge_pipeline.json').write_text(json.dumps(data))
    correct_knowledge(tmp_path,dict(action='undo',action_id=result['action_id']))
    assert {r['title'] for r in list_knowledge(tmp_path,category='preferences')['items']}=={'concise','detailed'}


def test_failed_transaction_restores_ledger_and_managed_exports(tmp_path,monkeypatch):
    prepare(tmp_path)
    from selfos.storage import files
    original=files._atomic_write
    failed=False
    def fail_once(path,content):
        nonlocal failed
        if path.name=='preferences.md' and not failed:
            failed=True;raise OSError('synthetic write interruption')
        return original(path,content)
    monkeypatch.setattr(files,'_atomic_write',fail_once)
    with pytest.raises(OSError,match='interruption'):edit(tmp_path)
    assert not load_corrections(tmp_path)['actions']
    assert list_knowledge(tmp_path,category='preferences')['items'][0]['title']=='concise'


def test_corrupted_ledger_does_not_fail_open(tmp_path):
    prepare(tmp_path)
    (tmp_path/'.knowledge_corrections.json').write_text('bad JSON')
    with pytest.raises(ValueError):list_knowledge(tmp_path)


def test_agent_context_uses_the_manual_projection(tmp_path):
    from selfos.app.chat import load_vault_context
    prepare(tmp_path);edit(tmp_path)
    text=load_vault_context(tmp_path)
    assert 'Balanced explanations' in text
    assert 'I prefer concise explanations.' not in text


def test_lesson_correction_updates_managed_export_without_removing_manual_notes(tmp_path):
    data=prepare(tmp_path)
    lesson=dict(text='Measure before optimizing.',domain='work',kind='inference',source_ids=['m2'])
    data['lessons']=[lesson]
    (tmp_path/'.knowledge_pipeline.json').write_text(json.dumps(data))
    path=tmp_path/'05_Life/lessons.md';path.parent.mkdir()
    path.write_text('# Reusable lessons'+chr(10)+'Manual note: keep this.'+chr(10)+chr(10)+
                    '- [inference] Measure before optimizing.'+chr(10)+'  Source: m2'+chr(10))
    row=list_knowledge(tmp_path,category='lessons')['items'][0]
    correct_knowledge(tmp_path,dict(action='edit',ids=[row['id']],patch={'text':'Profile before optimizing.'}))
    text=path.read_text()
    assert 'Manual note: keep this.' in text
    assert '[user_correction] Profile before optimizing.' in text
    assert '[inference] Measure before optimizing.' not in text


def test_rebuild_publication_uses_current_canonical_corrections(tmp_path):
    from selfos.app.pipeline import install_rebuilt
    from selfos.storage.files import _atomic_write
    vault=tmp_path/'vault';vault.mkdir()
    data=prepare(vault)
    scratch=tmp_path/'scratch';scratch.mkdir()
    staged={**data,'quality_version':2}
    (scratch/'.knowledge_pipeline.json').write_text(json.dumps(staged))
    for name,content in record_writes(scratch,staged).items():_atomic_write(scratch/name,content)
    edit(vault)  # Correction arrived after the rebuild snapshot was created.
    ledger_before=(vault/'.knowledge_corrections.json').read_bytes()
    install_rebuilt(vault,scratch)
    assert (vault/'.knowledge_corrections.json').read_bytes()==ledger_before
    assert 'Balanced explanations' in (vault/'knowledge/preferences.md').read_text()
    assert json.loads((vault/'.knowledge_pipeline.json').read_text())['preferences'][0]['value']=='concise'


def test_status_counts_use_the_same_correction_view(tmp_path):
    from selfos.app.knowledge import get_status
    prepare(tmp_path)
    row=list_knowledge(tmp_path,category='preferences')['items'][0]
    correct_knowledge(tmp_path,dict(action='delete',ids=[row['id']]))
    assert get_status(tmp_path)['counts']['preferences']==0


def test_rebuild_refinement_receives_distinct_user_correction_context(tmp_path):
    from selfos.app.knowledge import run_knowledge
    from tests.test_knowledge_service import source, summarize, refine
    roots,path=source(tmp_path);vault=tmp_path/'vault'
    assert run_knowledge(vault,roots=[roots],summarize=summarize,refine=refine)['installed']
    row=list_knowledge(vault,category='projects')['items'][0]
    correct_knowledge(vault,dict(action='edit',ids=[row['id']],patch={'text':'User corrected project purpose'}))
    seen=[]
    def inspect(payload):
        seen.append(payload.get('user_corrections'))
        return refine(payload)
    result=run_knowledge(vault,roots=[roots],summarize=summarize,refine=inspect,rebuild=True)
    assert result['installed']
    assert seen and seen[0]['project']['intent']=='User corrected project purpose'
    generated=json.loads((vault/'.knowledge_pipeline.json').read_text())
    assert next(iter(generated['cards'].values()))['intent']!='User corrected project purpose'
    assert list_knowledge(vault,category='projects')['items'][0]['summary']=='User corrected project purpose'


def test_project_export_edit_delete_and_undo_preserve_manual_notes(tmp_path):
    from tests.test_project_knowledge_contract import card
    from selfos.storage.documents import render_project_document
    from selfos.knowledge.identity import digest
    data=prepare(tmp_path);project=card(project_id='synthetic-project')
    data['cards']={project['project_id']:project}
    (tmp_path/'.knowledge_pipeline.json').write_text(json.dumps(data))
    path=tmp_path/'02_Work/projects'/(digest(project['project_id'])+'.md');path.parent.mkdir(parents=True)
    path.write_text('Manual project note.'+chr(10))
    path.write_bytes(render_project_document(tmp_path,project))
    row=list_knowledge(tmp_path,category='projects')['items'][0]
    correct_knowledge(tmp_path,dict(action='edit',ids=[row['id']],patch={'text':'Corrected purpose'}))
    assert 'Corrected purpose' in path.read_text() and 'Manual project note.' in path.read_text()
    row=list_knowledge(tmp_path,category='projects')['items'][0]
    deleted=correct_knowledge(tmp_path,dict(action='delete',ids=[row['id']]))
    assert 'Corrected purpose' not in path.read_text() and 'Manual project note.' in path.read_text()
    correct_knowledge(tmp_path,dict(action='undo',action_id=deleted['action_id']))
    assert 'Corrected purpose' in path.read_text()


def test_retry_of_a_saved_request_returns_the_same_action_and_backup(tmp_path):
    prepare(tmp_path)
    row=list_knowledge(tmp_path,category='preferences')['items'][0]
    request=dict(action='edit',ids=[row['id']],patch={'text':'Balanced explanations','value':'balanced'},
                 request_id='synthetic-request-0001')
    first=correct_knowledge(tmp_path,request)
    second=correct_knowledge(tmp_path,request)
    assert first==second
    assert len(load_corrections(tmp_path)['actions'])==1
    with pytest.raises(ValueError,match='request'):
        correct_knowledge(tmp_path,{**request,'patch':{'value':'different'}})


@pytest.mark.parametrize('field,value', [('originals', []), ('originals', [None]),
    ('anchors', [None]), ('versions', None), ('active', 'false'),
    ('category', 'unknown'), ('dependencies', [None]), ('patch', {'source_ids': ['fake']}), ('patch', {})])
def test_malformed_ledger_fails_closed_before_projection(tmp_path, field, value):
    prepare(tmp_path); edit(tmp_path)
    ledger=load_corrections(tmp_path)
    ledger['actions'][0][field]=value
    (tmp_path/'.knowledge_corrections.json').write_text(json.dumps(ledger))
    with pytest.raises(ValueError,match='correction'):
        load_corrections(tmp_path)


def test_aliased_project_correction_exports_and_exposes_new_candidate(tmp_path):
    from tests.test_project_knowledge_contract import card
    from selfos.knowledge.identity import digest
    data=prepare(tmp_path); original=card(project_id='old-project')
    data['cards']={'old-project':original}
    (tmp_path/'.knowledge_pipeline.json').write_text(json.dumps(data))
    row=list_knowledge(tmp_path,category='projects')['items'][0]
    correct_knowledge(tmp_path,dict(action='edit',ids=[row['id']],patch={'text':'Corrected purpose'}))
    data['project_aliases']={'old-project':'canonical-project'}
    data['cards']={'canonical-project':{**original,'project_id':'canonical-project','intent':'New supported purpose','source_ids':['new-source']}}
    (tmp_path/'.knowledge_pipeline.json').write_text(json.dumps(data))
    writes=record_writes(tmp_path,data)
    text=writes['02_Work/projects/'+digest('canonical-project')+'.md'].decode()
    assert '[user_correction]' in text and 'Corrected purpose' in text
    assert 'New supported purpose' in text
    row=list_knowledge(tmp_path,category='projects')['items'][0]
    detail=knowledge_detail(tmp_path,row['id'])['item']
    assert detail['proposed_revision']['intent']=='New supported purpose'


def test_agent_context_keeps_unmanaged_lesson_notes_without_suppressed_generated_text(tmp_path):
    from selfos.app.chat import load_vault_context
    data=prepare(tmp_path)
    lesson={'text':'Measure before optimizing.','kind':'inference','source_ids':['m1']}
    data['lessons']=[lesson]
    (tmp_path/'.knowledge_pipeline.json').write_text(json.dumps(data))
    path=tmp_path/'05_Life/lessons.md'; path.parent.mkdir()
    path.write_text('Manual lesson: check assumptions.\n- [inference] Measure before optimizing.\n  Source: m1\n')
    row=list_knowledge(tmp_path,category='lessons')['items'][0]
    correct_knowledge(tmp_path,dict(action='delete',ids=[row['id']]))
    context=load_vault_context(tmp_path)
    assert 'Manual lesson: check assumptions.' in context
    assert 'Measure before optimizing.' not in context


def test_value_only_correction_is_authoritative_in_exports_and_agent_context(tmp_path):
    from selfos.app.chat import load_vault_context
    prepare(tmp_path)
    row=list_knowledge(tmp_path,category='preferences')['items'][0]
    correct_knowledge(tmp_path,dict(action='edit',ids=[row['id']],patch={'value':'balanced'}))
    exported=(tmp_path/'knowledge/preferences.md').read_text()
    context=load_vault_context(tmp_path)
    assert 'balanced' in exported and 'balanced' in context
    assert 'I prefer concise explanations.' not in exported+context
