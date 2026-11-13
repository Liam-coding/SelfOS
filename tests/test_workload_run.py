"""Real loopback imports stop at allowance and reuse saved extraction on resume."""
from selfos.app.knowledge import run_knowledge
from selfos.app.budget import save_budget
from selfos.providers.settings import save_config
from tests.browser.integration_fixture import create_profile, ModelFixture


def test_budget_exhaustion_preserves_canonical_state_and_resume_keeps_quota(tmp_path):
    with ModelFixture() as model:
        profile = create_profile(tmp_path)
        vault = profile['vault']
        canonical = (vault / '.knowledge_pipeline.json').read_bytes()
        save_config(tmp_path, {'provider': 'openai', 'model': 'fixture-model', 'base_url': model.base_url,
                              'api_key': 'synthetic-fixture-key', 'proxy_mode': 'direct'})
        save_budget(vault, tmp_path, {'max_requests': 1})
        result = run_knowledge(vault, roots=[profile['source_root']], max_workers=1)
        assert result['status'] == 'stopped' and result['budget_exhausted']
        assert result['model_calls'] == len(model.requests) == 1
        assert (vault / '.knowledge_pipeline.json').read_bytes() == canonical
        assert result['request_usage']['used'] == 1
        first_session = model.extraction_sessions[0]
        repeat = run_knowledge(vault, roots=[profile['source_root']], max_workers=1)
        assert repeat['status'] == 'stopped' and len(model.requests) == 1
        save_budget(vault, tmp_path, {'max_requests': 100})
        resumed = run_knowledge(vault, roots=[profile['source_root']], max_workers=1)
        assert resumed['status'] == 'completed' and resumed['installed']
        assert model.extraction_sessions.count(first_session) == 1
        assert resumed['request_usage']['used'] == len(model.requests)
        assert resumed['request_usage']['missing_usage'] == len(model.requests)
        assert resumed['model_calls'] == len(model.requests) - 1
        assert all(path.read_bytes() == raw for path, raw in profile['original_bytes'].items())


def test_existing_provider_callbacks_cannot_bypass_transport_allowance(tmp_path):
    from selfos.providers.knowledge import api_summarizer, api_refiner
    with ModelFixture() as model:
        profile = create_profile(tmp_path)
        vault = profile['vault']
        save_config(tmp_path, {'provider': 'openai', 'model': 'fixture-model', 'base_url': model.base_url,
                              'api_key': 'synthetic-fixture-key', 'proxy_mode': 'direct'})
        save_budget(vault, tmp_path, {'max_requests': 1})
        result = run_knowledge(vault, roots=[profile['source_root']], max_workers=1,
            summarize=api_summarizer(tmp_path), refine=api_refiner(tmp_path))
        assert result['status'] == 'stopped'
        assert result['model_calls'] == len(model.requests) == 1
