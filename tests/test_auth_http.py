import json,threading
from http.server import ThreadingHTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import pytest
import serve
from selfos_auth import AuthManager

@pytest.fixture
def http(tmp_path,monkeypatch):
    monkeypatch.setattr(serve,'ROOT',tmp_path/'app');monkeypatch.setattr(serve,'VAULT',tmp_path/'app/vault')
    server=ThreadingHTTPServer(('127.0.0.1',0),serve.Handler)
    server.auth=AuthManager(serve.ROOT,serve.VAULT,directory=tmp_path/'private')
    threading.Thread(target=server.serve_forever,daemon=True).start()
    def request(path,body=None,cookie=''):
        req=Request(f'http://127.0.0.1:{server.server_port}'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json','Cookie':cookie})
        try:r=urlopen(req)
        except HTTPError as e:r=e
        with r:
            raw=r.read();data=json.loads(raw) if 'application/json' in r.headers.get('Content-Type','') else raw.decode()
            return r.status,data,r.headers.get('Set-Cookie','')
    yield request,server.auth
    server.shutdown();server.server_close()

def test_all_data_and_action_routes_require_login(http):
    request,a=http
    for path in ['/__knowledge__','/__knowledge_item__','/__knowledge_source__','/__knowledge_settings__','/__model_settings__','/__knowledge_run__','/__staging__','/__knowledge_stream__','/__harvest_stream__']:
        assert request(path)[0]==401
    for path in ['/chat','/__knowledge_stop__','/__knowledge_settings__','/__knowledge_restore__','/__model_settings__','/__model_test__','/__harvest__']:
        assert request(path,{})[0]==401
    assert 'SelfOS' in request('/')[1]
    assert request('/auth/status')[1]['state']=='setup'

def test_setup_login_change_and_logout(http):
    request,a=http
    code,data,cookie=request('/auth/setup',{'password':'a sufficiently long password'})
    assert code==200 and 'HttpOnly' in cookie and 'SameSite=Strict' in cookie
    cookie=cookie.split(';')[0]
    assert request('/__knowledge_run__',cookie=cookie)[0]==200
    assert request('/auth/setup',{'password':'another long password'})[0]==400
    assert request('/auth/change',{'current_password':'a sufficiently long password','password':'another sufficiently long password'},cookie)[0]==200
    assert request('/__knowledge_run__',cookie=cookie)[0]==401
    code,data,cookie=request('/auth/login',{'password':'another sufficiently long password'})
    assert code==200
    cookie=cookie.split(';')[0]
    assert request('/auth/logout',{},cookie)[0]==200
    assert request('/__knowledge_run__',cookie=cookie)[0]==401

def test_missing_corrupt_and_expired_credentials_block_data(http):
    request,a=http;a.setup('a sufficiently long password')
    token=a.login('a sufficiently long password');cookie='selfos_session='+token
    key=next(iter(a.sessions));expiry,fingerprint=a.sessions[key];a.sessions[key]=(0,fingerprint)
    assert request('/__knowledge_run__',cookie=cookie)[0]==401
    for raw in ['null','[]','{}','{broken']:
        a.path.write_text(raw)
        assert request('/auth/status')[1]['state']=='locked'
        assert request('/auth/setup',{'password':'another sufficiently long password'})[0]==400
        assert request('/__knowledge_run__',cookie=cookie)[0]==401
    a.path.unlink();assert request('/auth/status')[1]['state']=='locked'
