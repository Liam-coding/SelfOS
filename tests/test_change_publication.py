"""Receipts prove canonical publication, never staging progress."""
import json
import hashlib
import pytest
from tests.test_knowledge_corrections import record, state

RUN='20261114T100000-123456abcdef'

def publish(vault, data, run=RUN, index=1):
    from selfos.app.change_publication import publish_changes
    writes={'.knowledge_pipeline.json':json.dumps(data).encode()}
    publish_changes(vault,writes,run,index,kind='import')

def test_canonical_publication_binds_head_root_and_state(tmp_path):
    from selfos.storage.change_receipts import read_head, read_root, read_part
    publish(tmp_path,state(record()))
    head=read_head(tmp_path)
    root=read_root(tmp_path,head['audit_tip'])
    assert root['kind']=='import' and root['counts']['added']==1
    assert root['audit_parent'] is None and head['state_tip']==head['audit_tip']
    assert head['hashes']['state']==hashlib.sha256((tmp_path/'.knowledge_pipeline.json').read_bytes()).hexdigest()
    part=read_part(tmp_path,head['audit_tip'],1)
    assert part['changes'][0]['after'][0]['record']['value']=='concise'

def test_scratch_commit_has_no_audit_head(tmp_path):
    from selfos.storage.pipeline import commit
    commit(tmp_path,{'.knowledge_pipeline.json':b'{}'},RUN,1)
    assert not (tmp_path/'.knowledge_change_head.json').exists()

def test_no_change_publication_retains_zero_count_operation(tmp_path):
    from selfos.storage.change_receipts import read_head,read_root
    publish(tmp_path,{})
    root=read_root(tmp_path,read_head(tmp_path)['audit_tip'])
    assert root['change_count']==0 and root['parts']==[]

def test_same_identity_retry_is_idempotent_but_different_content_rejected(tmp_path):
    from selfos.storage.change_receipts import read_head
    publish(tmp_path,state(record()))
    original=read_head(tmp_path)
    publish(tmp_path,state(record()))
    assert read_head(tmp_path)==original
    with pytest.raises(ValueError,match='identity'):
        publish(tmp_path,state(record('detailed')))

def test_tampered_receipt_is_rejected(tmp_path):
    from selfos.storage.change_receipts import read_head,read_root
    publish(tmp_path,{})
    ref=read_head(tmp_path)['audit_tip']
    (tmp_path/'.knowledge_backups'/RUN/'000001'/'change-receipt.json').write_text('{}')
    with pytest.raises(ValueError,match='hash'):
        read_root(tmp_path,ref)

def test_invalid_identity_and_path_escape_fail_before_publication(tmp_path):
    with pytest.raises(ValueError):publish(tmp_path,{},run='../outside')
    assert not (tmp_path/'.knowledge_pipeline.json').exists()

def test_oversized_entry_rejects_before_canonical_write(tmp_path,monkeypatch):
    import selfos.storage.change_receipts as receipts
    monkeypatch.setattr(receipts,'PART_LIMIT',256)
    with pytest.raises(ValueError,match='limit'):
        publish(tmp_path,state(record()))
    assert not (tmp_path/'.knowledge_pipeline.json').exists()

def test_failed_canonical_write_rolls_back_head_and_hides_prepared_receipt(tmp_path,monkeypatch):
    import selfos.storage.files as files
    from selfos.storage.change_receipts import read_head
    publish(tmp_path,{})
    head=read_head(tmp_path)
    write=files._atomic_write
    failed=False
    def interrupted(path,content):
        nonlocal failed
        if path.name=='.knowledge_pipeline.json' and not failed:
            failed=True
            raise OSError('synthetic interruption')
        return write(path,content)
    monkeypatch.setattr(files,'_atomic_write',interrupted)
    with pytest.raises(OSError):publish(tmp_path,state(record()),index=2)
    assert read_head(tmp_path)==head
    assert json.loads((tmp_path/'.knowledge_pipeline.json').read_text())=={}

def test_changed_canonical_state_does_not_extend_verified_head(tmp_path):
    publish(tmp_path,{})
    (tmp_path/'.knowledge_pipeline.json').write_text('{"changed":true}')
    with pytest.raises(ValueError,match='canonical'):
        publish(tmp_path,state(record()),index=2)

def test_prepared_but_rolled_back_operation_can_retry(tmp_path,monkeypatch):
    import selfos.storage.files as files
    from selfos.storage.change_receipts import read_head
    original=files._atomic_write
    failed=False
    def interrupt(path,content):
        nonlocal failed
        if path.name=='.knowledge_pipeline.json' and not failed:
            failed=True
            raise OSError('interrupt once')
        return original(path,content)
    monkeypatch.setattr(files,'_atomic_write',interrupt)
    with pytest.raises(OSError):publish(tmp_path,state(record()))
    assert read_head(tmp_path) is None
    publish(tmp_path,state(record()))
    assert read_head(tmp_path)['audit_tip']['run_id']==RUN

def test_retry_identity_covers_managed_markdown_too(tmp_path):
    from selfos.app.change_publication import publish_changes
    publish_changes(tmp_path,{'knowledge/preferences.md':b'first'},RUN,1,kind='import')
    with pytest.raises(ValueError,match='identity'):
        publish_changes(tmp_path,{'knowledge/preferences.md':b'changed'},RUN,1,kind='import')

def test_parts_are_hash_verified_and_source_metadata_is_deduplicated(tmp_path,monkeypatch):
    import selfos.storage.change_receipts as receipts
    monkeypatch.setattr(receipts,'PART_LIMIT',2000)
    data=state(*[{**record(str(i)),'key':'setting.'+str(i)} for i in range(5)])
    data['sources']={'m1':{'role':'user','path':'synthetic'}}
    publish(tmp_path,data)
    ref=receipts.read_head(tmp_path)['audit_tip']
    root=receipts.read_root(tmp_path,ref)
    assert len(root['parts'])>1
    parts=[receipts.read_part(tmp_path,ref,p['number']) for p in root['parts']]
    assert sum(len(p['changes']) for p in parts)==5
    assert all(p['sources']=={'m1':data['sources']['m1']} for p in parts)
