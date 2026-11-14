import base64
import copy
import pytest
from tests.test_change_publication import publish,RUN
from tests.test_knowledge_corrections import state,record

def test_audit_export_recent_preserves_complete_ops_and_declares_boundary(tmp_path):
    from selfos.app.change_migration import audit_export
    publish(tmp_path,state(record()))
    publish(tmp_path,state(record('new')),'20261114T100001-123456abcdef')
    result=audit_export(tmp_path,mode='recent',recent=1)
    assert len(result['manifest']['included'])==1
    assert result['manifest']['omitted_parent']['run_id']==RUN
    assert result['summary']['operations']==1 and result['summary']['earlier_history_omitted']

def test_portable_audit_roundtrip_and_no_history_baseline(tmp_path):
    from selfos.app.migration import export_package,import_package
    from selfos.app.changes import list_changes
    vault=tmp_path/'source';vault.mkdir()
    publish(vault,state(record()))
    package=export_package(vault,tmp_path,audit='all')
    assert package['version']==2 and package['audit']['omitted_parent'] is None
    destination=tmp_path/'destination'
    import_package(destination,tmp_path/'new-root',package)
    assert list_changes(destination,session='a')['total']==1
    baseline=export_package(vault,tmp_path,audit='none')
    assert baseline['version']==1 and '.knowledge_change_head.json' not in baseline['files']
    import_package(tmp_path/'baseline',tmp_path/'baseline-root',baseline)
    assert list_changes(tmp_path/'baseline',session='a')['items']==[]

def test_tampered_or_missing_audit_part_fails_before_any_import_write(tmp_path):
    from selfos.app.migration import export_package,import_package
    vault=tmp_path/'source';vault.mkdir();publish(vault,state(record()))
    package=export_package(vault,tmp_path,audit='all')
    name=next(name for name in package['files'] if '/changes-' in name)
    for broken in (False,True):
        changed=copy.deepcopy(package)
        if broken:changed['files'][name]=base64.b64encode(b'{}').decode()
        else:del changed['files'][name]
        with pytest.raises(ValueError):import_package(tmp_path/'target',tmp_path/'new-root',changed)
        assert not (tmp_path/'target/.knowledge_pipeline.json').exists()

def test_selected_audit_limit_rejects_instead_of_clipping(tmp_path,monkeypatch):
    import selfos.app.change_migration as migration
    publish(tmp_path,state(record()))
    monkeypatch.setattr(migration,'EXPORT_LIMIT',100)
    with pytest.raises(ValueError,match='limit'):migration.audit_export(tmp_path,mode='all')

def test_recent_restore_target_omission_is_explicit(tmp_path):
    from selfos.storage.pipeline import restore_pipeline_backup
    from selfos.app.migration import export_package,import_package
    from selfos.app.changes import change_detail
    vault=tmp_path/'source';vault.mkdir();publish(vault,state(record()))
    restore_pipeline_backup(vault,RUN)
    package=export_package(vault,tmp_path,audit='recent',audit_recent=1)
    import_package(tmp_path/'target',tmp_path/'new-root',package)
    assert change_detail(tmp_path/'target',RUN+':1',session='a')['status']=='not_included'

def test_migrated_historical_uploaded_source_uses_included_local_original(tmp_path):
    import json
    from tests.test_upload_organization import uploaded
    from tests.test_knowledge_service import summarize,refine
    from selfos.app.uploads import upload_preview,organize_uploads
    from selfos.app.migration import export_package,import_package
    from selfos.app.changes import list_changes,change_source
    vault=tmp_path/'source';vault.mkdir();doc=uploaded(vault)
    preview=upload_preview(vault,[doc['id']])
    assert organize_uploads(vault,preview['id'],summarize=summarize,refine=refine)['installed']
    data=json.loads((vault/'.knowledge_pipeline.json').read_text())
    source_id=next(iter(data['sources']))
    publish(vault,{},RUN)
    package=export_package(vault,tmp_path,audit='all',include_originals=True)
    destination=tmp_path/'target';import_package(destination,tmp_path/'new-root',package)
    page=list_changes(destination,session='a')
    result=change_source(destination,RUN+':1',source_id,session='a',proof=page['cursor'])
    assert result['status']=='verified' and result['text']
    assert json.loads((destination/'.knowledge_pipeline.json').read_text())=={}
