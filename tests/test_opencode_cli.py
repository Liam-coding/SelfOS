import sys
from selfos.app.harness_previews import prepare_native
from selfos.sources.selection import save_sources
from tests.test_opencode_database import create_database


def test_native_cli_dry_run_resolves_preview_without_writes_or_model(tmp_path, monkeypatch, capsys):
    from selfos.app import knowledge_cli
    path, selection, _ = create_database(tmp_path, count=1)
    vault = tmp_path/'vault'
    vault.mkdir()
    save_sources(vault, selection)
    preview = prepare_native(vault, selection['entries'][0])
    before = {str(p.relative_to(vault)):p.read_bytes() for p in vault.rglob('*') if p.is_file()}
    def forbidden(*args, **kwargs): raise AssertionError('Dry run must not scan unrelated sources or call models')
    monkeypatch.setattr(knowledge_cli, 'extract_conversations', forbidden)
    monkeypatch.setattr(knowledge_cli, 'api_summarizer', forbidden)
    monkeypatch.setattr(sys, 'argv', ['selfos knowledge','--vault',str(vault),'--native-preview',preview['id'],'--dry-run'])
    knowledge_cli.main()
    after = {str(p.relative_to(vault)):p.read_bytes() for p in vault.rglob('*') if p.is_file()}
    assert before == after
    assert 'OpenCode' in capsys.readouterr().out
