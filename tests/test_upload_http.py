"""Loopback upload boundary checks using synthetic documents only."""
import http.client
import json
import socket
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import quote
from types import SimpleNamespace

import pytest

from selfos.security.auth import AuthManager
from selfos.web import server as web
from selfos.web.routes.auth import AuthRoutes


@pytest.fixture
def upload_http(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'ROOT', tmp_path / 'app')
    monkeypatch.setattr(web, 'VAULT', tmp_path / 'app/vault')
    monkeypatch.setattr(web.Handler, '_auth_guard', AuthRoutes._auth_guard)
    monkeypatch.setattr(web.Handler, '_session_alive', AuthRoutes._session_alive)
    def unexpected(*args, **kwargs):
        pytest.fail('Upload/list must not scan conversations or invoke a model')
    monkeypatch.setattr(web, '_call_claude', unexpected)
    monkeypatch.setattr(web, 'subprocess', SimpleNamespace(Popen=unexpected))
    server = ThreadingHTTPServer(('127.0.0.1', 0), web.Handler)
    server.auth = AuthManager(web.ROOT, web.VAULT, directory=tmp_path / 'private')
    server.auth.setup('Synthetic sufficiently long password')
    token = server.auth.login('Synthetic sufficiently long password')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def request(path='/__knowledge_upload__', body=b'Synthetic document.', headers=None, authenticated=True, method='POST'):
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        connection.putrequest(method, path)
        if authenticated:
            connection.putheader('Cookie', 'selfos_session=' + token)
        for key, value in (headers if headers is not None else [
                ('Content-Length', str(len(body))), ('Content-Type', 'application/octet-stream'),
                ('X-SelfOS-Filename', quote('summary.md'))]):
            connection.putheader(key, value)
        connection.endheaders(body if body else None)
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result
    yield request, server, web.VAULT
    server.shutdown()
    server.server_close()
    thread.join()


def test_upload_and_list_preserve_original_and_duplicate_identity(upload_http):
    request, _, vault = upload_http
    raw = bytes([239, 187, 191]) + b'# Synthetic description: stable checkpoints.'
    status, first = request(body=raw)
    assert status == 201
    assert (vault / first['document']['path']).read_bytes() == raw
    status, duplicate = request(body=raw)
    assert status == 200 and duplicate['duplicate']
    assert duplicate['document']['id'] == first['document']['id']
    status, page = request('/__knowledge_uploads__?offset=0&limit=1', body=b'', headers=[], method='GET')
    assert status == 200 and page['total'] == 1
    assert page['items'][0]['id'] == first['document']['id']


@pytest.mark.parametrize('headers,expected', [
    ([], 411),
    ([('Content-Length', '1'), ('Content-Length', '2')], 400),
    ([('Content-Length', '1'), ('Content-Length', '1')], 400),
    ([('Content-Length', '1, 1')], 400),
    ([('Content-Length', '-1')], 400),
    ([('Content-Length', '0')], 400),
    ([('Content-Length', str(20 * 1024 * 1024 + 1))], 413),
    ([('Content-Length', '1'), ('Transfer-Encoding', 'chunked')], 400),
    ([('Content-Length', '1'), ('Content-Type', 'application/json')], 415),
    ([('Content-Length', '1'), ('Content-Type', 'application/octet-stream')], 400),
    ([('Content-Length', '1'), ('Content-Type', 'application/octet-stream'), ('X-SelfOS-Filename', '%FF.md')], 400),
    ([('Content-Length', '1'), ('Content-Type', 'application/octet-stream'), ('X-SelfOS-Filename', '../evil.md')], 400),
    ([('Content-Length', '1'), ('Content-Type', 'application/octet-stream'), ('X-SelfOS-Filename', '%ZZ.md')], 400),
])
def test_invalid_headers_reject_without_admission(upload_http, headers, expected):
    request, _, vault = upload_http
    status, _ = request(body=b'x', headers=headers)
    assert status == expected
    assert not list(vault.rglob('originals/*.txt'))


@pytest.mark.parametrize('authenticated,extra,expected', [
    (False, [], 401),
    (True, [('Origin', 'https://example.test')], 403),
    (True, [('Sec-Fetch-Site', 'cross-site')], 403),
])
def test_guard_rejects_before_waiting_for_declared_body(upload_http, authenticated, extra, expected):
    request, _, vault = upload_http
    headers = [('Content-Length', '100000'), ('Content-Type', 'application/octet-stream'),
               ('X-SelfOS-Filename', 'summary.txt'), *extra]
    assert request(body=b'', headers=headers, authenticated=authenticated)[0] == expected
    assert not vault.exists()


def test_list_requires_auth_and_rejects_ambiguous_pagination(upload_http):
    request, _, _ = upload_http
    assert request('/__knowledge_uploads__', body=b'', headers=[], method='GET', authenticated=False)[0] == 401
    assert request('/__knowledge_uploads__?limit=1&limit=2', body=b'', headers=[], method='GET')[0] == 400


def test_disconnected_incomplete_body_leaves_no_admission(upload_http):
    _, server, vault = upload_http
    token = server.auth.login('Synthetic sufficiently long password')
    with socket.create_connection(('127.0.0.1', server.server_port), timeout=3) as connection:
        raw = ('POST /__knowledge_upload__ HTTP/1.1\r\n'
               f'Host: 127.0.0.1:{server.server_port}\r\n'
               f'Cookie: selfos_session={token}\r\n'
               'Content-Length: 100\r\nContent-Type: application/octet-stream\r\n'
               'X-SelfOS-Filename: summary.txt\r\n\r\nShort').encode()
        connection.sendall(raw)
        connection.shutdown(socket.SHUT_WR)
        received = b''
        while True:
            part = connection.recv(4096)
            if not part:
                break
            received += part
    assert b'400' in received.split(b'\r\n', 1)[0]
    assert not list(vault.rglob('originals/*.txt'))
    assert not list(vault.rglob('incoming/*.tmp'))


def test_stream_timeout_leaves_no_ready_entry(upload_http, monkeypatch):
    from selfos.web.routes import uploads
    monkeypatch.setattr(uploads, 'UPLOAD_TIMEOUT', 0.05)
    request, _, vault = upload_http
    headers = [('Content-Length', '100'), ('Content-Type', 'application/octet-stream'),
               ('X-SelfOS-Filename', 'summary.txt')]
    assert request(body=b'', headers=headers)[0] == 408
    assert not list(vault.rglob('originals/*.txt'))
    assert not list(vault.rglob('incoming/*.tmp'))
