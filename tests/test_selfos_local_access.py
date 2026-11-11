import selfos.web.server as _web_server
import subprocess as _subprocess
import json,threading
from http.server import ThreadingHTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import pytest


@pytest.fixture
def local_http(tmp_path,monkeypatch):
    monkeypatch.setattr(_web_server,'ROOT',tmp_path)
    monkeypatch.setattr(_web_server,'VAULT',tmp_path/'vault')
    monkeypatch.setattr(_web_server,'DASHBOARD',tmp_path/'dashboard.html')
    (tmp_path/'dashboard.html').write_text('local dashboard')
    staging=tmp_path/'vault/91_Staging';staging.mkdir(parents=True)
    (staging/'example.md').write_text('---\ntarget: vault/02_Work/result.md\n---\nExample content',encoding='utf-8')
    calls=[]
    monkeypatch.setattr(_web_server,'_get_config',lambda:('fake','https://api.invalid'))
    monkeypatch.setattr(_web_server,'_call_claude',lambda *args:calls.append('api') or 'test reply')
    class Completed:
        returncode=0;stdout='test complete';stderr=''
    monkeypatch.setattr(_subprocess,'run',lambda *args,**kwargs:calls.append('harvest') or Completed())
    server=ThreadingHTTPServer(('127.0.0.1',0),_web_server.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    def request(path,body=None,headers=None,method=None):
        req=Request(f'http://127.0.0.1:{server.server_port}'+path,
            data=None if body is None else json.dumps(body).encode(),headers=headers or {},method=method)
        try:response=urlopen(req)
        except HTTPError as error:response=error
        with response:return response.status,dict(response.headers),response.read()
    yield request,calls,tmp_path,server.server_port
    server.shutdown();server.server_close()


@pytest.mark.parametrize('path,body',[('/__staging__',None),('/__knowledge_settings__',None),('/__harvest__',{}),('/chat',{'messages':[{'role':'user','content':'test'}]}),('/__staging__/apply',{'files':['example.md']})])
def test_legacy_routes_reject_external_origin_before_any_side_effect(local_http,path,body):
    request,calls,root,_=local_http
    for headers in ({'Origin':'https://external.example'},{'Sec-Fetch-Site':'cross-site'}):
        status,_,_=request(path,body,headers)
        assert status==403
    assert calls==[] and (root/'vault/91_Staging/example.md').exists()
    assert not (root/'vault/02_Work/result.md').exists()


def test_rebinding_host_and_external_preflight_are_rejected(local_http):
    request,_,_,port=local_http
    assert request('/__knowledge__',headers={'Host':f'external.example:{port}','Origin':f'http://external.example:{port}'})[0]==403
    assert request('/chat',headers={'Origin':'https://external.example'},method='OPTIONS')[0]==403


def test_local_browser_and_cli_still_work_without_wildcard_cors(local_http):
    request,calls,_,port=local_http
    status,headers,_=request('/',headers={'Origin':f'http://127.0.0.1:{port}','Sec-Fetch-Site':'same-origin'})
    assert status==200 and headers.get('Access-Control-Allow-Origin')!='*'
    assert request('/chat',{'messages':[{'role':'user','content':'test'}]})[0]==200
    assert calls==['api']


def test_staging_apply_cannot_read_outside_its_staging_directory(local_http):
    request,_,root,_=local_http
    outside=root/'vault/outside.md'
    outside.write_text('---\ntarget: vault/02_Work/result.md\n---\nOutside content')
    status,_,body=request('/__staging__/apply',{'files':['../outside.md']})
    assert status==200 and json.loads(body)['errors']
    assert outside.exists() and not (root/'vault/02_Work/result.md').exists()


@pytest.mark.parametrize('target',['outside.md','vault/../outside.md','vault/91_Staging/example.md','vault/02_Work/result.json'])
def test_staging_apply_rejects_targets_outside_canonical_markdown(local_http,target):
    request,_,root,_=local_http
    source=root/'vault/91_Staging/example.md'
    source.write_text('---\ntarget: '+target+'\n---\nNew content')
    before=source.read_bytes()
    status,_,body=request('/__staging__/apply',{'files':['example.md']})
    assert status==200 and json.loads(body)['errors']
    assert source.read_bytes()==before
    assert not (root/'outside.md').exists() and not (root/'vault/02_Work/result.json').exists()


def test_valid_staging_apply_still_writes_canonical_markdown(local_http):
    request,_,root,_=local_http
    status,_,body=request('/__staging__/apply',{'files':['example.md']})
    assert status==200 and json.loads(body)['applied']==['example.md']
    assert (root/'vault/02_Work/result.md').read_text()=='Example content'
