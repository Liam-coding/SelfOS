import selfos.providers.knowledge as _providers_knowledge
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request
import pytest
from selfos.providers.settings import save_config
from selfos.providers.client import request_opener, test_connection as connection_check

@pytest.fixture
def api():
    captured=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            captured.append((self.path,dict(self.headers),body))
            if self.path.startswith('/v1/messages'):
                tool=body.get('tools',[{'name':'connection_check'}])[0]['name']
                result={'content':[{'type':'tool_use','name':tool,'input':{'ok':True}}]}
            else:
                tool=body['tools'][0]['function']['name']
                args={'ok':True} if tool=='connection_check' else {'project':None,'lessons':[],'personal_facts':[],'preferences':[],'history':[]}
                result={'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[{'function':{'name':tool,'arguments':json.dumps(args)}}]}}]}
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    yield f'http://127.0.0.1:{server.server_port}',captured
    server.shutdown();server.server_close()

@pytest.mark.parametrize('provider',['anthropic','openai'])
def test_real_http_connection_probe(api,tmp_path,provider):
    base,captured=api
    save_config(tmp_path,{'provider':provider,'model':'test-model','base_url':base+('/v1' if provider=='openai' else ''),'api_key':'test-secret','proxy_mode':'manual','proxy_url':'http://127.0.0.1:1'})
    assert connection_check(tmp_path)['ok']  # local endpoints bypass an unavailable proxy
    path,headers,body=captured[0]
    assert body['model']=='test-model'
    assert path==('/v1/chat/completions' if provider=='openai' else '/v1/messages')
    headers={k.lower():v for k,v in headers.items()}
    assert headers.get('authorization')=='Bearer test-secret' if provider=='openai' else headers.get('x-api-key')=='test-secret'

def test_actual_knowledge_extraction_uses_openai(api,tmp_path):

    from tests.test_project_knowledge_contract import session
    base,captured=api
    save_config(tmp_path,{'provider':'openai','model':'test-model','base_url':base+'/v1','proxy_mode':'direct'})
    result=_providers_knowledge.api_summarizer(tmp_path,review_records=False)(session())
    assert result['project'] is None and result['lessons']==[]
    assert captured[0][2]['tools'][0]['function']['name']=='retain_knowledge'

def test_anthropic_default_model_preserved(tmp_path):
    from selfos.providers.client import adapt_request
    from selfos.providers.settings import load_config
    body={'model':'claude-sonnet-4-6','max_tokens':100,'messages':[]}
    request=adapt_request(Request('https://unused',data=json.dumps(body).encode()),load_config(tmp_path))
    assert json.loads(request.data)['model']=='claude-sonnet-4-6'

def test_http_proxy_routes_remote_model_request(api,tmp_path,monkeypatch):
    base,captured=api
    monkeypatch.setenv('NO_PROXY','')
    save_config(tmp_path,{'provider':'openai','model':'test-model','base_url':'http://model.invalid/v1','proxy_mode':'manual','proxy_url':base})
    assert connection_check(tmp_path)['ok']
    assert captured[0][0]=='http://model.invalid/v1/chat/completions'
