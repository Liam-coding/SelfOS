"""A bounded sample cannot replace or upgrade unrelated historical knowledge."""
import copy
import json

from tests.test_knowledge_service import source, summarize, refine


def test_old_schema_sample_preserves_unrelated_card_and_global_coverage(tmp_path):
    from selfos.app.knowledge import run_knowledge
    from selfos.app.onboarding import build_preview
    from selfos.sources.selection import save_sources
    root, path = source(tmp_path)
    vault = tmp_path / "vault"
    assert run_knowledge(vault, roots=[root], summarize=summarize, refine=refine)["installed"]
    state_path = vault / ".knowledge_pipeline.json"
    previous = json.loads(state_path.read_text())
    previous["schema_version"] = 1
    previous["quality_version"] = 1
    previous["policy_hash"] = "legacy-policy"
    previous["cards"]["C:/projects/alpha"]["decisions"] = [f"Legacy decision {i}" for i in range(20)]
    state_path.write_text(json.dumps(previous), encoding="utf-8")
    new_root = tmp_path / "new-source"
    new_root.mkdir()
    (new_root / "beta.jsonl").write_text(path.read_text().replace("alpha", "beta").replace("original", "new-session").replace("reliable import", "bounded onboarding"), encoding="utf-8")
    save_sources(vault, {"roots": [str(new_root)], "exclusions": []})
    preview = build_preview(vault)
    seen = []
    def refine_sample(payload):
        seen.append(payload["project"]["project_id"])
        return refine(payload)
    result = run_knowledge(vault, sample_id=preview["id"], summarize=summarize, refine=refine_sample)
    assert result["installed"], result
    current = json.loads(state_path.read_text())
    assert current["cards"]["C:/projects/alpha"] == previous["cards"]["C:/projects/alpha"]
    assert current["schema_version"] == 1 and current["quality_version"] == 1
    assert current["policy_hash"] == "legacy-policy"
    assert seen == ["C:/projects/beta"]
    assert preview["id"] in current["sample_coverage"]


def test_invalid_sample_never_falls_back_to_local_discovery(tmp_path, monkeypatch):
    from selfos.app.knowledge import run_knowledge
    import selfos.app.knowledge as knowledge
    monkeypatch.setattr(knowledge, "local_roots", lambda: (_ for _ in ()).throw(AssertionError("default discovery")))
    result = run_knowledge(tmp_path / "vault", sample_id="../invalid",
                           summarize=lambda _: (_ for _ in ()).throw(AssertionError("model call")))
    assert result["status"] == "failed"
    assert not result["installed"]


def test_context_excludes_cached_private_text_without_deleting_history(tmp_path):
    from selfos.app.knowledge_context import filter_project_context
    from tests.test_project_knowledge_contract import card
    root = tmp_path / "sources"
    selection = {"roots": [str(root)], "exclusions": [str(root / "private.jsonl")]}
    public = card(project_id="project", source_ids=["public"], intent="Build a reliable public application")
    private = card(project_id="project", source_ids=["private"], intent="PRIVATE CLIENT SECRET")
    state = {"sources": {"public": {"path": str(root / "public.jsonl"), "project_id": "project"},
                         "private": {"path": str(root / "private.jsonl"), "project_id": "project"}},
             "summaries": {"public": {"project": public}, "private": {"project": private}}}
    payload = {"project": private, "lessons": [{"text": "PRIVATE CLIENT SECRET", "source_ids": ["public", "private"]}],
               "sources": state["sources"], "intent_history": [{"intent": "PRIVATE CLIENT SECRET"}]}
    before = copy.deepcopy(state)
    filtered = filter_project_context(payload, state, selection)
    assert "PRIVATE CLIENT SECRET" not in json.dumps(filtered)
    assert filtered["project"]["intent"] == "Build a reliable public application"
    assert filtered["lessons"] == []
    assert state == before


def test_custom_registered_source_can_be_viewed_but_exclusion_denies_it(tmp_path):
    from selfos.app.knowledge import run_knowledge
    from selfos.app.library import knowledge_source
    from selfos.sources.selection import save_sources
    root, _ = source(tmp_path)
    vault = tmp_path / "vault"
    result = run_knowledge(vault, roots=[root], summarize=summarize, refine=refine)
    assert result['installed']
    state = json.loads((vault / '.knowledge_pipeline.json').read_text())
    identity = next(iter(state['sources']))
    save_sources(vault, {'roots': [str(root)], 'exclusions': []})
    assert 'I prefer Chinese' in json.dumps(knowledge_source(vault, identity))
    save_sources(vault, {'roots': [str(root)], 'exclusions': [str(root)]})
    import pytest
    with pytest.raises(ValueError):
        knowledge_source(vault, identity)


def test_cli_dry_run_uses_only_validated_preview(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    from selfos.app.onboarding import build_preview
    from selfos.sources.selection import save_sources
    root, _ = source(tmp_path)
    vault = tmp_path / 'vault'
    save_sources(vault, {'roots': [str(root)], 'exclusions': []})
    preview = build_preview(vault)
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')}
    command = [sys.executable, '-m', 'selfos', 'knowledge', '--vault', str(vault),
               '--dry-run', '--onboarding-preview', preview['id']]
    result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'Scanned 1 messages' in result.stdout
    command[-1] = '../invalid'
    result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=20)
    assert result.returncode != 0


def test_registered_exclusions_filter_real_pipeline_cache_and_keep_local_lessons(tmp_path):
    from selfos.app.knowledge import run_knowledge
    from selfos.sources.selection import save_sources
    root, path = source(tmp_path)
    vault = tmp_path / 'vault'
    def private_summary(item):
        result = summarize(item)
        result['project']['intent'] = 'PRIVATE CLIENT SECRET'
        return result
    assert run_knowledge(vault, roots=[root], summarize=private_summary, refine=refine)['installed']
    state_path = vault / '.knowledge_pipeline.json'
    state = json.loads(state_path.read_text())
    private_id = next(iter(state['sources']))
    private_lesson = {'text': 'PRIVATE CLIENT SECRET', 'source_ids': [private_id], 'domain': 'work', 'kind': 'inference'}
    state['lessons'].append(private_lesson)
    state['lesson_history'].append(private_lesson)
    state_path.write_text(json.dumps(state), encoding='utf-8')
    (root / 'public.jsonl').write_text(path.read_text().replace('original', 'public-session').replace('reliable import', 'public-only UI'), encoding='utf-8')
    save_sources(vault, {'roots': [str(root)], 'exclusions': [str(path)]})
    captured = []
    def public_summary(item):
        assert Path(item['messages'][0]['path']).name == 'public.jsonl'
        result = summarize(item)
        result['project']['intent'] = 'Build public-only UI'
        return result
    from pathlib import Path
    def public_refiner(payload):
        captured.append(copy.deepcopy(payload))
        return refine(payload)
    result = run_knowledge(vault, summarize=public_summary, refine=public_refiner)
    assert result['installed'], result
    assert captured and 'PRIVATE CLIENT SECRET' not in json.dumps(captured)
    current = json.loads(state_path.read_text())
    assert private_lesson in current['lessons']
    assert any(summary.get('project', {}).get('intent') == 'PRIVATE CLIENT SECRET' for summary in current['summaries'].values())


def test_exhaustion_reports_charged_attempts_not_rejected_retries(tmp_path):
    from selfos.app.onboarding import build_preview
    from selfos.app.knowledge import run_knowledge
    from selfos.sources.selection import save_sources
    from selfos.storage.onboarding import SampleBudget
    root, _ = source(tmp_path)
    vault = tmp_path / 'vault'
    save_sources(vault, {'roots': [str(root)], 'exclusions': []})
    preview = build_preview(vault)
    budget = SampleBudget(vault, preview['id'])
    for _ in range(11):
        budget.claim()
    def failing_attempt(item):
        budget.claim()
        raise ValueError('Synthetic invalid response')
    result = run_knowledge(vault, sample_id=preview['id'], summarize=failing_attempt, refine=refine)
    assert result['status'] == 'failed' and not result['installed']
    assert result['model_calls'] == 1
    assert result['request_budget'] == {'used': 12, 'remaining': 0, 'limit': 12}
