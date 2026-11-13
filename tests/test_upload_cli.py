import io
import json

from selfos.app.uploads import upload_preview
from selfos.sources.upload_admission import admit_document
from tests.test_knowledge_service import summarize, refine


def test_cli_upload_preview_uses_selected_document_without_harness_discovery(tmp_path, monkeypatch, capsys):
    from selfos.app import knowledge_cli as cli
    from selfos.app import knowledge
    raw = b'I prefer Chinese. We are building reliable import.'
    vault = tmp_path / 'vault'
    doc = admit_document(vault, 'summary.md', io.BytesIO(raw), len(raw))['document']
    preview = upload_preview(vault, [doc['id']])
    def forbidden(*args, **kwargs):
        raise AssertionError('Upload CLI must not discover conversations')
    monkeypatch.setattr(knowledge, 'extract_conversations', forbidden)
    from selfos.providers import knowledge as providers
    monkeypatch.setattr(providers, 'api_summarizer', lambda *args, **kwargs: summarize)
    monkeypatch.setattr(providers, 'api_refiner', lambda *args, **kwargs: refine)
    monkeypatch.setattr('sys.argv', ['knowledge', '--root', str(tmp_path), '--upload-preview', preview['id']])
    cli.main()
    output = capsys.readouterr().out
    assert 'selected uploaded documents' in output
    assert 'scanning local Claude' not in output
    saved = json.loads((vault / '.knowledge_pipeline.json').read_text(encoding='utf-8'))
    assert {s['document_id'] for s in saved['sources'].values()} == {doc['id']}
