"""Request allowance is cumulative, durable and independent of import locks."""
from concurrent.futures import ThreadPoolExecutor
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _preview(tmp_path):
    from selfos.app.onboarding import build_preview
    from selfos.sources.selection import save_sources
    root = tmp_path / "source"
    root.mkdir()
    save_sources(tmp_path / "vault", {"roots": [str(root)], "exclusions": []})
    return build_preview(tmp_path / "vault")


def test_budget_shared_between_instances_and_cannot_reset(tmp_path):
    from selfos.storage.onboarding import SampleBudget, ModelBudgetExceeded
    preview = _preview(tmp_path)
    vault = tmp_path / "vault"
    for _ in range(12):
        SampleBudget(vault, preview["id"]).claim()
    assert SampleBudget(vault, preview["id"]).status() == {"used": 12, "remaining": 0, "limit": 12}
    with pytest.raises(ModelBudgetExceeded):
        SampleBudget(vault, preview["id"]).claim()


def test_parallel_claims_never_exceed_allowance(tmp_path):
    from selfos.storage.onboarding import SampleBudget, ModelBudgetExceeded
    preview = _preview(tmp_path)
    def claim(_):
        try:
            SampleBudget(tmp_path / "vault", preview["id"]).claim()
            return True
        except ModelBudgetExceeded:
            return False
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert sum(pool.map(claim, range(18))) == 12


def test_missing_corrupt_budget_or_invalid_id_fails_closed(tmp_path):
    from selfos.storage.onboarding import SampleBudget
    preview = _preview(tmp_path)
    vault = tmp_path / "vault"
    budget = vault / ".knowledge_onboarding" / "budgets" / (preview["id"] + ".json")
    budget.write_text('{"used": -1, "limit": 12}', encoding="utf-8")
    with pytest.raises(ValueError):
        SampleBudget(vault, preview["id"]).claim()
    budget.unlink()
    with pytest.raises(ValueError):
        SampleBudget(vault, preview["id"]).claim()
    with pytest.raises(ValueError):
        SampleBudget(vault, "../escape").claim()


def test_process_restart_keeps_consumed_allowance(tmp_path):
    from selfos.storage.onboarding import SampleBudget
    preview = _preview(tmp_path)
    vault = tmp_path / "vault"
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    script = "from selfos.storage.onboarding import SampleBudget; import sys; b=SampleBudget(sys.argv[1],sys.argv[2]); [b.claim() for _ in range(4)]"
    processes = [subprocess.Popen([sys.executable, "-c", script, str(vault), preview["id"]], env=env)
                 for _ in range(3)]
    assert all(process.wait(timeout=20) == 0 for process in processes)
    assert SampleBudget(vault, preview["id"]).status()["remaining"] == 0


def test_budget_status_does_not_create_or_modify_files(tmp_path):
    from selfos.storage.onboarding import SampleBudget
    preview = _preview(tmp_path)
    vault = tmp_path / 'vault'
    before = {str(path.relative_to(vault)): path.read_bytes() for path in vault.rglob('*') if path.is_file()}
    assert SampleBudget(vault, preview['id']).status()['remaining'] == 12
    after = {str(path.relative_to(vault)): path.read_bytes() for path in vault.rglob('*') if path.is_file()}
    assert after == before
