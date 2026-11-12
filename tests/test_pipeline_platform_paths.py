import json
from pathlib import Path
import pytest

from selfos.storage.pipeline import commit, recover, restore_pipeline_backup, safe_path


def test_relative_vault_is_canonicalized_for_commit_and_restore(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vault=Path('data/vault')
    vault.mkdir(parents=True)
    run_id='20261112T120000-123456abcdef'
    commit(vault,{'.knowledge_pipeline.json':b'{}'},run_id,1)
    assert safe_path(vault,'.knowledge_pipeline.json') == (vault/'.knowledge_pipeline.json').resolve()
    assert (vault/'.knowledge_pipeline.json').read_bytes()==b'{}'
    restore_pipeline_backup(vault,run_id)
    assert not (vault/'.knowledge_pipeline.json').exists()


def test_relative_vault_journal_recovery_uses_same_boundary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vault=Path('vault');vault.mkdir()
    (vault/'.knowledge_pipeline.json').write_text('{}')
    (vault/'.knowledge_pending.json').write_text(json.dumps({'.knowledge_pipeline.json':None}))
    recover(vault)
    assert not (vault/'.knowledge_pipeline.json').exists()
    assert not (vault/'.knowledge_pending.json').exists()


def test_symlinked_vault_root_can_commit_and_restore(tmp_path):
    actual=tmp_path/'actual';actual.mkdir()
    alias=tmp_path/'alias'
    try:
        alias.symlink_to(actual,target_is_directory=True)
    except OSError:
        pytest.skip('Creating directory symlinks requires additional OS privileges')
    vault=alias/'vault';vault.mkdir()
    run_id='20261112T120001-123456abcdef'
    commit(vault,{'.knowledge_pipeline.json':b'{}'},run_id,1)
    assert (actual/'vault/.knowledge_pipeline.json').read_bytes()==b'{}'
    restore_pipeline_backup(vault,run_id)
    assert not (actual/'vault/.knowledge_pipeline.json').exists()
