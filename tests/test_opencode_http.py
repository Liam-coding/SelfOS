import json

from tests.test_upload_http import upload_http
from test_opencode_database import create_database
from selfos.sources.selection import save_sources


def test_authenticated_native_preview_does_not_start_a_model_or_jsonl_scan(upload_http, tmp_path):
    request, server, vault = upload_http
    path, selection, _ = create_database(tmp_path, count=1)
    save_sources(vault, selection)
    raw = json.dumps({'entry': selection['entries'][0]}).encode()
    headers = [('Content-Length', str(len(raw))), ('Content-Type', 'application/json')]
    status, preview = request('/__knowledge_native_preview__', body=raw, headers=headers)
    assert status == 200 and 0 < len(preview['sessions']) <= 2
    status, _ = request('/__knowledge_native_preview__', body=raw, headers=headers, authenticated=False)
    assert status == 401
    status, _ = request('/__knowledge_native_preview__', body=raw, headers=headers + [('Origin', 'https://unrelated.example')])
    assert status == 403


def test_native_stream_rejects_mixing_preview_kinds_before_subprocess(upload_http):
    request, _, _ = upload_http
    status, _ = request('/__knowledge_stream__?native_preview=' + 'a'*32 + '&upload_preview=' + 'b'*32,
                        body=b'', headers=[], method='GET')
    assert status == 400
