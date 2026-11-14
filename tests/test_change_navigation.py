"""Bounded session-bound ancestry verification before exposing snapshots."""
import pytest
from tests.test_change_publication import publish,RUN
from tests.test_knowledge_corrections import state,record

def test_list_proves_membership_and_detail_retains_before_after(tmp_path):
    from selfos.app.changes import list_changes,change_detail
    publish(tmp_path,state(record()))
    page=list_changes(tmp_path,session='session-a')
    assert page['total']==1 and not page['has_more']
    detail=change_detail(tmp_path,page['items'][0]['id'],session='session-a',cursor=page['cursor'])
    assert detail['status']=='verified' and detail['items'][0]['after'][0]['record']['value']=='concise'

def test_proofs_cannot_cross_sessions(tmp_path):
    from selfos.app.changes import list_changes,change_detail
    publish(tmp_path,state(record()))
    page=list_changes(tmp_path,session='a')
    with pytest.raises(ValueError):
        change_detail(tmp_path,page['items'][0]['id'],session='b',cursor=page['cursor'])

def test_changed_head_invalidates_proof_without_exposing_old_detail(tmp_path):
    from selfos.app.changes import list_changes,change_detail
    publish(tmp_path,state(record()))
    page=list_changes(tmp_path,session='a')
    publish(tmp_path,state(record('new')),'20261114T100001-123456abcdef')
    detail=change_detail(tmp_path,page['items'][0]['id'],session='a',cursor=page['cursor'])
    assert detail['status']=='reset_required' and not detail.get('items')
    assert list_changes(tmp_path,session='a',cursor=detail['cursor'])['items']

def test_bounded_deep_link_does_not_expose_unproven_snapshots(tmp_path,monkeypatch):
    import selfos.app.changes as changes
    publish(tmp_path,state(record()))
    publish(tmp_path,state(record('new')),'20261114T100001-123456abcdef')
    monkeypatch.setattr(changes,'ROOTS_PER_REQUEST',1)
    page=changes.list_changes(tmp_path,session='a')
    assert page['total'] is None and page['has_more']
    detail=changes.change_detail(tmp_path,RUN+':1',session='b')
    assert detail['status']=='verification_pending' and not detail.get('items')
    detail=changes.change_detail(tmp_path,RUN+':1',session='b',cursor=detail['cursor'])
    assert detail['status']=='verified'

def test_filter_change_and_expired_cursor_are_rejected(tmp_path,monkeypatch):
    from selfos.app.changes import list_changes
    import selfos.storage.change_cursors as cursors
    publish(tmp_path,state(record()))
    page=list_changes(tmp_path,session='a')
    with pytest.raises(ValueError):list_changes(tmp_path,session='a',cursor=page['cursor'],category='lessons')
    monkeypatch.setattr(cursors,'TTL',-1)
    with pytest.raises(ValueError):list_changes(tmp_path,session='a',cursor=page['cursor'])

def test_filtered_empty_page_still_continues(tmp_path,monkeypatch):
    import selfos.app.changes as changes
    publish(tmp_path,state(record()))
    publish(tmp_path,state(record('new')),'20261114T100001-123456abcdef')
    monkeypatch.setattr(changes,'ROOTS_PER_REQUEST',1)
    page=changes.list_changes(tmp_path,session='a',category='lessons')
    assert page['items']==[] and page['has_more'] and page['cursor']

def test_restore_marks_original_reverted_from_verified_refs(tmp_path):
    from selfos.app.changes import list_changes
    from selfos.storage.pipeline import restore_pipeline_backup
    publish(tmp_path,state(record()))
    restore_pipeline_backup(tmp_path,RUN)
    page=list_changes(tmp_path,session='a')
    old=next(item for item in page['items'] if item['id']==RUN+':1')
    assert old['state']=='reverted'

def test_unknown_deep_link_is_missing_after_verified_end(tmp_path):
    from selfos.app.changes import change_detail
    publish(tmp_path,{})
    result=change_detail(tmp_path,'20261114T100009-123456abcdef:1',session='a')
    assert result['status']=='missing' and not result.get('items')

def test_historical_source_is_verified_without_reinserting_metadata(tmp_path):
    import json
    from tests.test_document_pipeline import document
    from selfos.app.changes import list_changes,change_source
    vault,path,message=document(tmp_path)
    data=state(record(source=message['id']));data['sources']={message['id']:message}
    publish(vault,data)
    publish(vault,{},'20261114T100001-123456abcdef')
    original=(vault/'.knowledge_pipeline.json').read_bytes()
    page=list_changes(vault,session='a')
    result=change_source(vault,RUN+':1',message['id'],session='a',proof=page['cursor'])
    assert result['text']==message['text']
    assert (vault/'.knowledge_pipeline.json').read_bytes()==original
    path.write_bytes(b'changed original')
    with pytest.raises(ValueError) as error:
        change_source(vault,RUN+':1',message['id'],session='a',proof=page['cursor'])
    assert error.value.code=='source_changed'

def test_historical_source_obeys_current_privacy_exclusion(tmp_path):
    from tests.test_document_pipeline import document
    from selfos.sources.selection import save_sources
    from selfos.app.changes import list_changes,change_source
    vault,path,message=document(tmp_path)
    data=state(record(source=message['id']));data['sources']={message['id']:message}
    publish(vault,data)
    page=list_changes(vault,session='a')
    save_sources(vault,{'roots':[],'exclusions':[],'privacy_exclusions':[str(path)]})
    with pytest.raises(ValueError) as error:
        change_source(vault,RUN+':1',message['id'],session='a',proof=page['cursor'])
    assert error.value.code=='source_denied'

def test_cursor_cache_capacity_is_bounded(tmp_path,monkeypatch):
    import selfos.storage.change_cursors as cursors
    monkeypatch.setattr(cursors,'MAX_CURSORS',0)
    with pytest.raises(cursors.NavigationLimit):cursors.save(tmp_path,'a',{'proofs':{},'reverted':[]})

def test_head_changed_during_detail_read_returns_reset_without_snapshots(tmp_path,monkeypatch):
    import selfos.app.changes as changes
    publish(tmp_path,state(record()))
    page=changes.list_changes(tmp_path,session='a')
    original=changes._Budget.part
    def concurrent(budget,*args):
        result=original(budget,*args)
        publish(tmp_path,state(record('later')),'20261114T100009-123456abcdef')
        return result
    monkeypatch.setattr(changes._Budget,'part',concurrent)
    result=changes.change_detail(tmp_path,RUN+':1',session='a',cursor=page['cursor'])
    assert result['status']=='reset_required' and not result.get('items')

def test_sustained_navigation_reclaims_cursors_and_restart_still_works(tmp_path,monkeypatch):
    from selfos.app.changes import list_changes,change_detail
    import selfos.storage.change_cursors as cursors
    monkeypatch.setattr(cursors,'MAX_CURSORS',2)
    publish(tmp_path,state(record()))
    page=list_changes(tmp_path,session='a');cursor=page['cursor']
    for _ in range(8):
        detail=change_detail(tmp_path,RUN+':1',session='a',cursor=cursor)
        assert detail['status']=='verified';cursor=detail['cursor']
    assert list_changes(tmp_path,session='a')['items']
    assert list_changes(tmp_path,session='b')['items']

def test_current_record_lookup_returns_its_verified_historical_operation(tmp_path):
    from selfos.app.changes import record_change,change_detail
    from selfos.knowledge.identity import record_version
    publish(tmp_path,state(record()))
    version=record_version('preferences',record())
    result=record_change(tmp_path,version,session='a')
    assert result['status']=='verified' and result['id']==RUN+':1'
    assert change_detail(tmp_path,result['id'],session='a',cursor=result['cursor'])['items']
