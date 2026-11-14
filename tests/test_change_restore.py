"""State ancestry can rewind while audit ancestry always advances."""
import json
import pytest
from tests.test_change_publication import publish,RUN
from tests.test_knowledge_corrections import state,record

B='20261114T100001-123456abcdef'
C='20261114T100002-123456abcdef'

def test_restore_and_later_import_keep_independent_audit_and_state_tips(tmp_path):
    from selfos.storage.change_receipts import read_head,read_root
    from selfos.storage.pipeline import restore_pipeline_backup
    publish(tmp_path,state(record('a')))
    a=read_head(tmp_path)['audit_tip']
    publish(tmp_path,state(record('b')),B)
    b=read_head(tmp_path)['audit_tip']
    restore_pipeline_backup(tmp_path,B)
    head=read_head(tmp_path)
    restored=head['audit_tip']
    root=read_root(tmp_path,restored)
    assert head['state_tip']==a and restored!=a
    assert root['kind']=='restore' and root['audit_parent']==b and root['reverted_receipts']==[b]
    publish(tmp_path,state(record('c')),C)
    assert read_root(tmp_path,read_head(tmp_path)['audit_tip'])['audit_parent']==restored
    restore_pipeline_backup(tmp_path,C)
    assert read_head(tmp_path)['state_tip']==a
    assert json.loads((tmp_path/'.knowledge_pipeline.json').read_text())['preferences'][0]['value']=='a'
    with pytest.raises(ValueError):restore_pipeline_backup(tmp_path,B)
    with pytest.raises(ValueError):restore_pipeline_backup(tmp_path,restored['run_id'])

def test_restore_rejects_unrelated_state_ancestor(tmp_path):
    from selfos.storage.pipeline import restore_pipeline_backup
    publish(tmp_path,state(record('a')))
    publish(tmp_path,state(record('b')),B)
    with pytest.raises(ValueError):restore_pipeline_backup(tmp_path,RUN)
    assert json.loads((tmp_path/'.knowledge_pipeline.json').read_text())['preferences'][0]['value']=='b'

def test_restore_after_hash_mismatch_leaves_audit_and_files_untouched(tmp_path):
    from selfos.storage.pipeline import restore_pipeline_backup
    from selfos.storage.change_receipts import read_head
    publish(tmp_path,state(record()))
    head=read_head(tmp_path)
    (tmp_path/'.knowledge_pipeline.json').write_text('{"changed":true}')
    with pytest.raises(ValueError):restore_pipeline_backup(tmp_path,RUN)
    assert read_head(tmp_path)==head

def test_restore_marker_is_not_publication_proof(tmp_path):
    from selfos.storage.pipeline import restore_pipeline_backup
    from selfos.storage.change_receipts import read_head
    publish(tmp_path,state(record()))
    (tmp_path/'.knowledge_backups'/RUN/'restored').write_text('1')
    restore_pipeline_backup(tmp_path,RUN)
    assert read_head(tmp_path)['state_tip'] is None

def test_failed_restore_rolls_back_new_head_and_knowledge(tmp_path,monkeypatch):
    import selfos.storage.files as files
    from selfos.storage.pipeline import restore_pipeline_backup
    from selfos.storage.change_receipts import read_head
    publish(tmp_path,state(record('a')))
    publish(tmp_path,state(record('b')),B)
    head=read_head(tmp_path)
    original=files._atomic_write
    failed=False
    def interrupted(path,content):
        nonlocal failed
        if path.name=='.knowledge_pipeline.json' and not failed:
            failed=True;raise OSError('restore interrupted')
        return original(path,content)
    monkeypatch.setattr(files,'_atomic_write',interrupted)
    with pytest.raises(OSError):restore_pipeline_backup(tmp_path,B)
    assert read_head(tmp_path)==head
    assert json.loads((tmp_path/'.knowledge_pipeline.json').read_text())['preferences'][0]['value']=='b'
