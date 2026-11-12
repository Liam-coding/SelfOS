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
