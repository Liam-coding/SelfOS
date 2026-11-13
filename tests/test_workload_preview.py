"""Workload estimates are bounded, source-filtered and make no model requests."""
import json
from selfos.sources.selection import save_sources


def fixture_source(root, name='one'):
    root.mkdir(parents=True, exist_ok=True)
    path = root / (name + '.jsonl')
    rows = [{'type': 'session_meta', 'payload': {'id': name, 'cwd': str(root / 'project')}},
            {'type': 'response_item', 'timestamp': '2026-11-13T08:00:00Z', 'payload': {'type': 'message', 'role': 'user',
             'content': [{'type': 'input_text', 'text': f'I prefer explicit recovery for interrupted knowledge imports. Session {name}.'}]}}]
    path.write_text(chr(10).join(json.dumps(row) for row in rows), encoding='utf-8')
    return path


def test_preview_is_read_only_and_unknown_prices_are_not_zero(tmp_path):
    from selfos.app.workload import workload_preview
    root, vault = tmp_path / 'source', tmp_path / 'vault'
    fixture_source(root)
    save_sources(vault, {'roots': [str(root)], 'exclusions': []})
    before = {p: p.read_bytes() for p in vault.rglob('*') if p.is_file()}
    report = workload_preview(vault, tmp_path)
    assert report['messages_scanned'] == report['compact_parts'] == report['pending_parts'] == 1
    assert report['cached_parts'] == 0
    assert report['estimate']['cost_usd'] is None
    assert report['estimate']['calls']['low'] == 1
    assert report['estimate']['calls']['high'] > 1
    assert {p: p.read_bytes() for p in vault.rglob('*') if p.is_file()} == before


def test_preview_excludes_sources_and_bounds_file_reads(tmp_path):
    from selfos.app.workload import workload_preview
    root, vault = tmp_path / 'source', tmp_path / 'vault'
    for n in range(10):
        fixture_source(root, str(n))
    excluded = root / 'private'
    fixture_source(excluded, 'excluded')
    save_sources(vault, {'roots': [str(root)], 'exclusions': [str(excluded)]})
    result = workload_preview(vault, tmp_path)
    assert result['files_scanned'] == result['messages_scanned'] == 8
    assert result['bounded'] is True
    assert 'file_limit' in result['warnings']
    assert result['projects'] == 1


def test_cached_preview_uses_policy_augmented_fingerprints(tmp_path):
    from selfos.app.workload import workload_preview
    from selfos.app.knowledge import run_knowledge
    from tests.test_knowledge_service import refine
    from tests.test_project_knowledge_contract import card
    def summarize(item):
        message = item['messages'][0]
        return {'project': card(project_id=item['project_id'], source_ids=[message['id']],
            updated_at=message['timestamp'], domain='work'), 'lessons': []}
    root, vault = tmp_path / 'source', tmp_path / 'vault'
    fixture_source(root)
    save_sources(vault, {'roots': [str(root)], 'exclusions': []})
    assert run_knowledge(vault, roots=[root], summarize=summarize, refine=refine)['status'] == 'completed'
    preview = workload_preview(vault, tmp_path)
    assert preview['cached_parts'] == 1 and preview['pending_parts'] == 0
    assert preview['estimate']['calls']['low'] == 0
    assert preview['estimate']['calls']['high'] > 0
    from selfos.storage.settings import save_settings
    save_settings(vault, {'domains': ['work'], 'detail': 'detailed'})
    changed = workload_preview(vault, tmp_path)
    assert changed['pending_parts'] == 1 and changed['cached_parts'] == 0


def test_empty_preview_creates_no_files_and_has_no_estimated_requests(tmp_path, monkeypatch):
    from selfos.app.workload import workload_preview
    import selfos.sources.selection as selection
    monkeypatch.setattr(selection, 'local_roots', lambda: [])
    vault = tmp_path / 'absent-vault'
    result = workload_preview(vault, tmp_path)
    assert result['estimate']['calls'] == {'low': 0, 'high': 0}
    assert not vault.exists()


def test_preview_skips_oversized_checkpoint_before_reading_it(tmp_path, monkeypatch):
    from selfos.app import workload
    from pathlib import Path
    root, vault = tmp_path / 'source', tmp_path / 'vault'
    fixture_source(root)
    save_sources(vault, dict(roots=[str(root)], exclusions=[]))
    metadata = vault / '.knowledge_rebuild' / ('a' * 24) / '.knowledge_pipeline.json'
    metadata.parent.mkdir(parents=True)
    metadata.write_text(json.dumps(dict(cache={}, summaries={}, payload='x' * 512)))
    monkeypatch.setattr(workload, 'PREVIEW_METADATA_BYTES', 128, raising=False)
    read_text = Path.read_text
    def bounded_read(path, *args, **kwargs):
        if path == metadata:
            raise AssertionError('Preview read an oversized checkpoint')
        return read_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', bounded_read)
    report = workload.workload_preview(vault, tmp_path)
    assert report['pending_parts'] == 1
    assert report['bounded'] and 'checkpoint_limit' in report['warnings']


def test_duplicate_export_does_not_double_estimated_work(tmp_path):
    from selfos.app.workload import workload_preview
    root, vault = tmp_path / 'source', tmp_path / 'vault'
    original = fixture_source(root)
    (root / 'copy.jsonl').write_bytes(original.read_bytes())
    save_sources(vault, {'roots': [str(root)], 'exclusions': []})
    report = workload_preview(vault, tmp_path)
    assert report['files_scanned'] == 2
    assert report['messages_scanned'] == report['pending_parts'] == 1


def test_pricing_uses_explicit_rates_and_stale_model_rates_stay_unknown(tmp_path):
    from selfos.app.workload import workload_preview
    from selfos.app.budget import save_budget
    from selfos.providers.settings import save_config
    root, vault = tmp_path / 'source', tmp_path / 'vault'
    fixture_source(root)
    save_sources(vault, {'roots': [str(root)], 'exclusions': []})
    save_config(tmp_path, {'provider': 'openai', 'model': 'fixture', 'base_url': 'http://localhost:1234/v1'})
    save_budget(vault, tmp_path, {'input_price': 2, 'output_price': 8, 'max_requests': 8})
    estimate = workload_preview(vault, tmp_path)['estimate']
    assert estimate['cost_usd']['low'] == (estimate['input_tokens']['low'] * 2 + estimate['output_tokens']['low'] * 8) / 1000000
    assert estimate['cost_usd']['high'] > estimate['cost_usd']['low']
    save_config(tmp_path, {'model': 'different'})
    assert workload_preview(vault, tmp_path)['estimate']['cost_usd'] is None


def test_usage_from_other_model_cannot_be_priced_as_current_model(tmp_path):
    from selfos.storage.usage import RequestUsage
    from selfos.app.budget import model_identity, save_budget
    from selfos.app.workload import usage_status
    from selfos.providers.settings import save_config
    save_config(tmp_path, {'provider': 'openai', 'model': 'first', 'base_url': 'http://localhost:1234/v1'})
    vault = tmp_path / 'vault'
    meter = RequestUsage(vault, 'a' * 32, 10, model_identity=model_identity(tmp_path))
    ticket = meter.claim()
    meter.observe(ticket, {'usage': {'prompt_tokens': 100, 'completion_tokens': 20}}, 'openai')
    save_budget(vault, tmp_path, {'input_price': 2, 'output_price': 8})
    assert usage_status(vault, tmp_path)['runs'][0]['cost_usd'] == .00036
    save_config(tmp_path, {'model': 'second'})
    save_budget(vault, tmp_path, {'input_price': 4, 'output_price': 16})
    assert usage_status(vault, tmp_path)['runs'][0]['cost_usd'] is None
