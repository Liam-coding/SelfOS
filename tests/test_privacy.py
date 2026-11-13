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


def test_legacy_allowed_import_preserves_privacy_settings(tmp_path):
    from selfos.app.legacy_knowledge import import_knowledge
    from selfos.sources.selection import save_sources,load_sources
    root=tmp_path/'sources';root.mkdir();vault=tmp_path/'vault'
    selection=save_sources(vault,{'roots':[str(root)],'exclusions':[]})
    messages=[{'id':'a','text':'public source','path':str(root/'a.jsonl'),'source':'codex','role':'user','timestamp':'2026-01-01','project':'public'}]
    import_knowledge(vault,messages,lambda *args:[],progress=lambda _:None)
    assert load_sources(vault)==selection
    assert import_knowledge(vault,messages,lambda *args:[],progress=lambda _:None)['batches']==0


def migration_fixture():
    import base64
    return dict(format='selfos-portable', version=1, files={
        '.knowledge_pipeline.json': base64.b64encode(json.dumps(dict(cards={}, lessons=[], sources={})).encode()).decode()},
        settings=dict(provider='openai', model='local', base_url='http://localhost:9999/v1'))


def test_migration_model_config_failure_rolls_back_knowledge(tmp_path, monkeypatch):
    import selfos.app.migration as migration
    original = migration._atomic_write
    def write(path, raw):
        if path.name == '.selfos-model.json' or path.name.startswith('.selfos-model-'):
            raise OSError('synthetic config failure')
        return original(path, raw)
    monkeypatch.setattr(migration, '_atomic_write', write)
    vault = tmp_path / 'vault'
    with pytest.raises(OSError):
        migration.import_package(vault, tmp_path, migration_fixture())
    assert not (vault / '.knowledge_pipeline.json').exists()
    assert not (tmp_path / '.selfos-model.json').exists()
    monkeypatch.setattr(migration, '_atomic_write', original)
    assert migration.import_package(vault, tmp_path, migration_fixture())['imported'] == 1


def test_migration_preserves_existing_model_configuration(tmp_path):
    from selfos.app.migration import import_package
    config = tmp_path / '.selfos-model.json'
    original = b'{"provider":"anthropic","api_key":"synthetic-existing-key"}'
    config.write_bytes(original)
    with pytest.raises(ValueError, match='model configuration'):
        import_package(tmp_path / 'vault', tmp_path, migration_fixture())
    assert config.read_bytes() == original
    assert not (tmp_path / 'vault' / '.knowledge_pipeline.json').exists()


def test_export_checks_original_size_before_allocating(tmp_path, monkeypatch):
    import selfos.app.migration as migration
    vault = tmp_path / 'vault'
    original = vault / '.knowledge_uploads/originals/large.md'
    original.parent.mkdir(parents=True)
    original.write_bytes(b'x' * 32)
    monkeypatch.setattr(migration, 'MAX_BYTES', 16)
    read_bytes = Path.read_bytes
    def bounded_read(path):
        if path == original:
            raise AssertionError('allocated an oversized original')
        return read_bytes(path)
    monkeypatch.setattr(Path, 'read_bytes', bounded_read)
    with pytest.raises(ValueError, match='64 MiB'):
        migration.export_package(vault, tmp_path, include_originals=True)


def test_legacy_import_rechecks_privacy_before_commit(tmp_path):
    from selfos.app.legacy_knowledge import import_knowledge
    from selfos.sources.selection import save_sources
    from selfos.knowledge.contracts import STATE
    root = tmp_path / 'sources'
    root.mkdir()
    vault = tmp_path / 'vault'
    save_sources(vault, dict(roots=[str(root)], exclusions=[]))
    messages = [dict(id='a', text='public source', path=str(root / 'a.jsonl'),
        source='codex', role='user', timestamp='2026-01-01', project='public')]
    def generate(*args):
        save_sources(vault, dict(roots=[str(root)], exclusions=[str(root)]))
        return []
    with pytest.raises(ValueError, match='Privacy rules changed'):
        import_knowledge(vault, messages, generate, progress=lambda _: None)
    assert not (vault / STATE).exists()


@pytest.mark.parametrize('state', [
    {'sources': {}, 'cards': []},
    {'sources': {}, 'cards': {'p': []}},
    {'sources': {}, 'lessons': ['not a record']},
    {'sources': {}, 'preferences': {}},
    {'sources': {}, 'summaries': []},
    {'sources': {}, 'cards': {'p': {'source_ids': 's1'}}},
    {'sources': {}, 'summaries': {'s': {'lessons': ['not a record']}}},
    {'sources': {}, 'lessons': [{'text': 42, 'source_ids': []}]},
    {'sources': {}, 'cards': {'p': {'title': []}}},
    {'sources': {}, 'lessons': [{'text': 'lesson', 'source_ids': [], 'revision': 42}]},
    {'sources': {}, 'lessons': [{'text': 'lesson', 'source_ids': [], 'conflict_source_ids': 42}]},
    {'sources': {}, 'lessons': [{'text': 'lesson', 'source_ids': [], 'observed_at': 42}]},
])
def test_migration_rejects_invalid_consumer_state_without_writes(tmp_path, state):
    import base64
    from selfos.app.migration import import_package
    package = migration_fixture()
    package['files']['.knowledge_pipeline.json'] = base64.b64encode(json.dumps(state).encode()).decode()
    with pytest.raises(ValueError):
        import_package(tmp_path / 'vault', tmp_path, package)
    assert not (tmp_path / 'vault' / '.knowledge_pipeline.json').exists()
    assert not (tmp_path / '.selfos-model.json').exists()


@pytest.mark.parametrize('ledger', [
    {'version': 1, 'actions': [{}]},
    {'version': 1, 'actions': [], 'receipts': {'request': {'fingerprint': 42}}},
])
def test_migration_rejects_invalid_correction_ledger_without_writes(tmp_path, ledger):
    import base64
    from selfos.app.migration import import_package
    package = migration_fixture()
    package['files']['.knowledge_corrections.json'] = base64.b64encode(json.dumps(ledger).encode()).decode()
    with pytest.raises(ValueError):
        import_package(tmp_path / 'vault', tmp_path, package)
    assert not (tmp_path / 'vault' / '.knowledge_pipeline.json').exists()


def test_foreign_platform_migration_preserves_roots_and_rebases_private_upload(tmp_path):
    import base64
    import os
    from selfos.app.migration import import_package
    from selfos.sources.selection import load_sources
    from selfos.app.privacy import permitted_source
    origin = '/home/person/vault' if os.name == 'nt' else 'C:/Users/person/vault'
    harness = '/home/person/harness' if os.name == 'nt' else 'C:/Users/person/harness'
    original = origin + '/.knowledge_uploads/originals/private.md'
    selection = dict(version=1, roots=[harness], exclusions=[harness + '/secret'], privacy_exclusions=[original])
    state = dict(cards={}, lessons=[], sources={
        'external': dict(path=harness + '/a.jsonl'),
        'doc': dict(path=original, source='document')})
    package = migration_fixture()
    package.update(origin_vault=origin, origin_platform='posix' if os.name == 'nt' else 'nt')
    package['files'].update({
        '.knowledge_pipeline.json': base64.b64encode(json.dumps(state).encode()).decode(),
        '.knowledge_sources.json': base64.b64encode(json.dumps(selection).encode()).decode(),
        '.knowledge_uploads/originals/private.md': base64.b64encode(b'private original').decode()})
    vault = tmp_path / 'vault'
    result = import_package(vault, tmp_path, package)
    migrated = json.loads((vault / '.knowledge_pipeline.json').read_text())
    assert migrated['sources']['external']['path'] == harness + '/a.jsonl'
    assert next(s for s in result['sources'] if s['id'] == 'external')['status'] == 'unresolved'
    assert migrated['sources']['doc']['path'] == str(vault / '.knowledge_uploads/originals/private.md')
    assert next(s for s in result['sources'] if s['id'] == 'doc')['status'] == 'resolved'
    local = load_sources(vault)
    assert local['roots'] == []
    assert not permitted_source(migrated['sources']['doc'], local, vault)
    metadata = json.loads((vault / '.knowledge_migration.json').read_text())
    assert metadata['unresolved_selection'] == selection


def test_legacy_new_privacy_settings_during_generation_prevent_commit(tmp_path):
    from selfos.app.legacy_knowledge import import_knowledge
    from selfos.sources.selection import save_sources
    from selfos.knowledge.contracts import STATE
    root = tmp_path / 'source'
    root.mkdir()
    vault = tmp_path / 'vault'
    messages = [dict(id='a', text='public source', path=str(root / 'a.jsonl'),
        source='codex', role='user', timestamp='2026-01-01', project='public')]
    def generate(*args):
        save_sources(vault, dict(roots=[str(root)], exclusions=[str(root)]))
        return []
    with pytest.raises(ValueError, match='Privacy rules changed'):
        import_knowledge(vault, messages, generate, progress=lambda _: None)
    assert not (vault / STATE).exists()


def test_publication_boundary_rechecks_privacy_inside_install(tmp_path, monkeypatch):
    import selfos.app.knowledge as knowledge
    from selfos.sources.selection import save_sources
    from tests.test_knowledge_service import source, summarize, refine
    root, path = source(tmp_path)
    vault = tmp_path / 'vault'
    save_sources(vault, dict(roots=[str(root)], exclusions=[]))
    install = knowledge.install_rebuilt
    def change_privacy(*args, **kwargs):
        save_sources(vault, dict(roots=[str(root)], exclusions=[str(path)]))
        return install(*args, **kwargs)
    monkeypatch.setattr(knowledge, 'install_rebuilt', change_privacy)
    result = knowledge.run_knowledge(vault, roots=[root], summarize=summarize, refine=refine)
    assert not result['installed']
    assert not (vault / '.knowledge_pipeline.json').exists()


def test_migration_does_not_overwrite_model_config_created_during_import(tmp_path, monkeypatch):
    import selfos.app.migration as migration
    from selfos.providers.settings import save_config
    atomic_write = migration._atomic_write
    def create_config_while_writing_knowledge(path, raw):
        if path.name == '.knowledge_pipeline.json':
            save_config(tmp_path, dict(provider='openai', model='concurrent-model',
                base_url='http://localhost:9999/v1', api_key='synthetic-concurrent-key', proxy_mode='direct'))
        return atomic_write(path, raw)
    monkeypatch.setattr(migration, '_atomic_write', create_config_while_writing_knowledge)
    with pytest.raises(ValueError, match='model configuration'):
        migration.import_package(tmp_path / 'vault', tmp_path, migration_fixture())
    saved = json.loads((tmp_path / '.selfos-model.json').read_text())
    assert saved['api_key'] == 'synthetic-concurrent-key'
    assert saved['model'] == 'concurrent-model'
    assert not (tmp_path / 'vault' / '.knowledge_pipeline.json').exists()


def test_api_rule_write_cannot_race_actual_publication_commit(tmp_path, monkeypatch):
    import selfos.app.pipeline as pipeline
    from selfos.app.knowledge import run_knowledge
    from selfos.sources.selection import save_sources, load_sources
    from tests.test_knowledge_service import source, summarize, refine
    root, path = source(tmp_path)
    vault = tmp_path / 'vault'
    save_sources(vault, dict(roots=[str(root)], exclusions=[]))
    commit = pipeline.commit
    def change_rule_at_commit(target, *args, **kwargs):
        if target.resolve() == vault.resolve():
            save_sources(vault, dict(roots=[str(root)], exclusions=[str(path)]))
        return commit(target, *args, **kwargs)
    monkeypatch.setattr(pipeline, 'commit', change_rule_at_commit)
    result = run_knowledge(vault, roots=[root], summarize=summarize, refine=refine)
    assert not result['installed']
    assert load_sources(vault)['exclusions'] == []
    assert not (vault / '.knowledge_pipeline.json').exists()


def test_migration_coordinates_source_rule_writes(tmp_path, monkeypatch):
    import base64
    import selfos.app.migration as migration
    from selfos.sources.selection import save_sources
    root = tmp_path / 'source'
    root.mkdir()
    vault = tmp_path / 'vault'
    package = migration_fixture()
    package['files']['.knowledge_sources.json'] = base64.b64encode(json.dumps(dict(
        version=1, roots=[str(root)], exclusions=[])).encode()).decode()
    atomic_write = migration._atomic_write
    def change_selection(path, raw):
        if path.name == '.knowledge_pipeline.json':
            save_sources(vault, dict(roots=[str(root)], exclusions=[str(root)]))
        return atomic_write(path, raw)
    monkeypatch.setattr(migration, '_atomic_write', change_selection)
    with pytest.raises(ValueError, match='Privacy rules'):
        migration.import_package(vault, tmp_path, package)
    assert not (vault / '.knowledge_pipeline.json').exists()
    assert not (vault / '.knowledge_sources.json').exists()


@pytest.mark.parametrize('concurrent_replacement', [False, True])
def test_interruption_after_model_link_cleans_only_owned_config(tmp_path, monkeypatch, concurrent_replacement):
    import selfos.app.migration as migration
    from selfos.providers.settings import save_config
    link = migration.os.link
    def interrupted_link(source, destination):
        link(source, destination)
        if concurrent_replacement:
            save_config(tmp_path, dict(provider='openai', model='replacement',
                base_url='http://localhost:9999/v1', api_key='synthetic-replacement-key', proxy_mode='direct'))
        raise KeyboardInterrupt('synthetic interruption after publication')
    monkeypatch.setattr(migration.os, 'link', interrupted_link)
    with pytest.raises(KeyboardInterrupt):
        migration.import_package(tmp_path / 'vault', tmp_path, migration_fixture())
    assert not (tmp_path / 'vault' / '.knowledge_pipeline.json').exists()
    config = tmp_path / '.selfos-model.json'
    if concurrent_replacement:
        assert json.loads(config.read_text())['api_key'] == 'synthetic-replacement-key'
    else:
        assert not config.exists()
        monkeypatch.setattr(migration.os, 'link', link)
        assert migration.import_package(tmp_path / 'vault', tmp_path, migration_fixture())['imported'] == 1
