import selfos.web.server as _web_server
import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import pytest

from tests.test_knowledge_library import vault

@pytest.fixture
def http(vault,monkeypatch):
    monkeypatch.setattr(_web_server,'VAULT',vault)
    server=ThreadingHTTPServer(('127.0.0.1',0),_web_server.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    def request(path,headers=None):
        try:response=urlopen(Request(f'http://127.0.0.1:{server.server_port}'+path,headers=headers or {}))
        except HTTPError as error:response=error
        with response:return response.status,json.loads(response.read())
    yield request
    server.shutdown();server.server_close()

def test_browse_detail_and_errors(http):
    code,data=http('/__knowledge__?category=projects&query=checkpoints')
    assert code==200 and data['total']==1
    identity=data['items'][0]['id']
    assert http('/__knowledge_item__?id='+identity)[1]['item']['decisions']==['Use checkpoints']
    assert http('/__knowledge_item__?id=missing')[0]==404
    assert http('/__knowledge__?offset=-1')[0]==400
    assert http('/__knowledge__?limit=oops')[0]==400
    assert http('/__knowledge_item__?id='+identity+'&source_offset=-1')[0]==400
    assert http('/__knowledge_source__?id=missing')[0]==404

@pytest.mark.parametrize('path',['/__knowledge__','/__knowledge_item__?id=x','/__knowledge_source__?id=x','/__knowledge_run__'])
def test_private_views_reject_cross_site_reads(http,path):
    assert http(path,{'Origin':'https://outside.example'})[0]==403
    assert http(path,{'Sec-Fetch-Site':'cross-site'})[0]==403
