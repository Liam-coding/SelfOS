from tests.test_auth_http import http
from tests.test_knowledge_service import source, summarize, refine
from selfos.app.knowledge import run_knowledge


def test_authenticated_publication_status_reads_saved_work_without_scan(http, tmp_path, monkeypatch):
    request, auth = http
    auth.setup('synthetic publication password')
    token = auth.login('synthetic publication password')
    roots, _ = source(tmp_path)
    vault = tmp_path / 'app' / 'vault'
    stopped = [False]
    def progress(line):
        if line.startswith('Saved session '):
            stopped[0] = True
    run_knowledge(vault, roots=[roots], summarize=summarize, refine=refine,
                  cancel=lambda: stopped[0], progress=progress)
    before = {str(p.relative_to(vault)): p.read_bytes() for p in vault.rglob('*') if p.is_file()}
    def forbid(*args, **kwargs):
        raise AssertionError('Status must not scan sources')
    monkeypatch.setattr('selfos.app.knowledge.extract_conversations', forbid)
    assert request('/__knowledge_settings__')[0] == 401
    code, data, _ = request('/__knowledge_settings__', cookie='selfos_session=' + token)
    assert code == 200
    assert data['counts']['preferences'] == 0
    assert data['publication']['operations'][0]['staged_counts']['preferences'] == 1
    after = {str(p.relative_to(vault)): p.read_bytes() for p in vault.rglob('*') if p.is_file()}
    assert before == after
