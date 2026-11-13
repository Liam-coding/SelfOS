import json
from pathlib import Path
import pytest


def test_exclusion_covers_project_and_relative_upload(tmp_path):
    from selfos.app.privacy import permitted_source
    selection = {'roots': [str(tmp_path/'harness')], 'exclusions': [str(tmp_path/'secret'), str(tmp_path/'.knowledge_uploads/originals/private.md')]}
    assert not permitted_source({'path': str(tmp_path/'harness/a.jsonl'), 'project_id': str(tmp_path/'secret')}, selection, tmp_path)
    assert not permitted_source({'path': '.knowledge_uploads/originals/private.md', 'source': 'document'}, selection, tmp_path)
    assert permitted_source({'path': '.knowledge_uploads/originals/public.md', 'source': 'document'}, selection, tmp_path)


def test_mixed_source_knowledge_withheld_without_erasing_local_state(tmp_path):
    from selfos.app.privacy import model_state
    state = {'sources': {'a': {'path': str(tmp_path/'public/a')}, 'b': {'path': str(tmp_path/'secret/b')}},
             'cards': {'p': {'source_ids': ['a','b'], 'intent': 'private'}},
             'lessons': [{'source_ids': ['a'], 'text': 'public'}, {'source_ids': ['a','b'], 'text': 'private'}]}
    projected = model_state(state, {'roots':[str(tmp_path)], 'exclusions':[str(tmp_path/'secret')]}, tmp_path)
    assert projected['cards'] == {}
    assert [r['text'] for r in projected['lessons']] == ['public']
    assert state['cards']['p']['intent'] == 'private'


def test_roundtrip_excludes_credentials_and_reports_unresolved(tmp_path):
    from selfos.app.migration import export_package, import_package
    root = tmp_path/'old'; vault = root/'vault'; vault.mkdir(parents=True)
    state = {'cache':{}, 'cards':{}, 'lessons':[], 'sources':{'a':{'path':str(root/'missing.jsonl'), 'provenance':{'line':3}}}}
    (vault/'.knowledge_pipeline.json').write_text(json.dumps(state))
    (root/'.selfos-model.json').write_text(json.dumps({'provider':'openai','model':'local','base_url':'http://localhost:9999/v1','api_key':'NEVER_EXPORT','proxy_mode':'direct','proxy_url':''}))
    package = export_package(vault, root)
    assert 'NEVER_EXPORT' not in json.dumps(package)
    target = tmp_path/'new/vault'
    report = import_package(target, target.parent, package)
    assert json.loads((target/'.knowledge_pipeline.json').read_text())['sources'] == state['sources']
    assert report['sources'][0]['status'] == 'unresolved'
    assert 'api_key' not in json.loads((target.parent/'.selfos-model.json').read_text()) or not json.loads((target.parent/'.selfos-model.json').read_text())['api_key']


def test_import_rejects_escape_without_writes(tmp_path):
    from selfos.app.migration import import_package
    package = {'format':'selfos-portable','version':1,'files':{'../escape': 'eA=='},'settings':{}}
    with pytest.raises(ValueError): import_package(tmp_path/'vault',tmp_path,package)
    assert not (tmp_path/'vault').exists()


@pytest.mark.parametrize('rebuild',[False,True])
def test_excluded_harness_never_requested_on_incremental_or_rebuild(tmp_path,rebuild):
    from tests.test_knowledge_service import source, summarize, refine
    from selfos.app.knowledge import run_knowledge
    from selfos.sources.selection import save_sources
    root,path=source(tmp_path); vault=tmp_path/'vault'
    assert run_knowledge(vault,roots=[root],summarize=summarize,refine=refine)['installed']
    save_sources(vault,{'roots':[str(root)],'exclusions':[str(path)]})
    def forbidden(_): raise AssertionError('excluded text reached model')
    result=run_knowledge(vault,roots=[root],summarize=forbidden,refine=forbidden,rebuild=rebuild)
    assert result['model_calls']==0
    assert result['status']=='completed'


def test_rule_change_during_retry_prevents_next_model_request(tmp_path):
    from tests.test_knowledge_service import source, summarize, refine
    from selfos.app.knowledge import run_knowledge
    from selfos.sources.selection import save_sources
    root,path=source(tmp_path);vault=tmp_path/'vault'
    save_sources(vault,{'roots':[str(root)],'exclusions':[]})
    calls=[]
    def first(item):
        calls.append(item)
        save_sources(vault,{'roots':[str(root)],'exclusions':[str(path)]})
        raise ValueError('retry')
    result=run_knowledge(vault,roots=[root],summarize=first,refine=refine)
    assert len(calls)==1
    assert not result['installed']
    assert result['status']=='failed'


def test_uploaded_original_roundtrip_rebases_source(tmp_path):
    from selfos.app.migration import export_package,import_package
    old=tmp_path/'old/vault';original=old/'.knowledge_uploads/originals/a.md'
    original.parent.mkdir(parents=True);original.write_text('isolated original')
    state={'sources':{'doc':{'path':str(original),'source':'document','provenance':{'page':1}}},'cards':{},'lessons':[]}
    (old/'.knowledge_pipeline.json').write_text(json.dumps(state))
    package=export_package(old,old.parent,include_originals=True)
    new=tmp_path/'new/vault';report=import_package(new,new.parent,package)
    assert (new/'.knowledge_uploads/originals/a.md').read_text()=='isolated original'
    migrated=json.loads((new/'.knowledge_pipeline.json').read_text())['sources']['doc']
    assert migrated['path']==str(new/'.knowledge_uploads/originals/a.md')
    assert migrated['provenance']=={'page':1}
    assert report['sources'][0]['status']=='resolved'


def test_legacy_import_filters_excluded_sources_before_model(tmp_path):
    from selfos.app.legacy_knowledge import import_knowledge
    from selfos.sources.selection import save_sources
    root=tmp_path/'sources';root.mkdir();vault=tmp_path/'vault'
    path=root/'private.jsonl'
    save_sources(vault,{'roots':[str(root)],'exclusions':[str(path)]})
    messages=[{'id':'a','text':'private source','path':str(path),'source':'codex','role':'user','timestamp':'2026-01-01','project':'private'}]
    def forbidden(*args): raise AssertionError('excluded legacy input')
    assert import_knowledge(vault,messages,forbidden,progress=lambda _:None)['batches']==0


def test_migrated_uploaded_original_keeps_its_exclusion(tmp_path):
    from selfos.app.migration import export_package,import_package
    from selfos.app.privacy import permitted_source
    from selfos.sources.selection import save_sources,load_sources
    old=tmp_path/'old/vault';original=old/'.knowledge_uploads/originals/private.md'
    original.parent.mkdir(parents=True);original.write_text('private')
    (old/'.knowledge_pipeline.json').write_text(json.dumps({'sources':{'doc':{'path':str(original)}}}))
    save_sources(old,{'roots':[],'exclusions':[],'privacy_exclusions':[str(original)]})
    new=tmp_path/'new/vault'
    import_package(new,new.parent,export_package(old,old.parent,include_originals=True))
    state=json.loads((new/'.knowledge_pipeline.json').read_text())
    assert not permitted_source(state['sources']['doc'],load_sources(new),new)


def test_nested_transport_guard_rechecks_policy(tmp_path):
    from selfos.app.privacy import request_scope,check_request_scope,selection_hash
    from selfos.sources.selection import save_sources
    root=tmp_path/'source';root.mkdir();vault=tmp_path/'vault';source={'path':str(root/'a')}
    save_sources(vault,{'roots':[str(root)],'exclusions':[]})
    with request_scope(vault,selection_hash(vault),[source]):
        check_request_scope()
        save_sources(vault,{'roots':[str(root)],'exclusions':[str(root)]})
        with pytest.raises(ValueError,match='Privacy rules changed'): check_request_scope()
    check_request_scope()
