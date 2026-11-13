import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from selfos.providers.settings import save_config, load_config
from tests.test_knowledge_settings_http import http
import selfos.web.server as server

def test_model_discovery_has_explicit_control_and_keeps_manual_entry():
    from selfos.web.rendering.resources import frontend_text
    html=frontend_text('templates/settings-model.html')
    assert 'id="model-load-models"' in html
    assert 'id="model-available"' in html
    assert '<input id="model-name" required' in html

@pytest.fixture
def model_api(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY','')
    requests = []
    state = {'status': 200, 'body': {'data': [{'id': 'z-model'}, {'id': 'a-model'}, {'id': 'z-model'}]}}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, dict(self.headers)))
            self.send_response(state['status']); self.end_headers()
            body=state['body'](self.path) if callable(state['body']) else state['body']
            self.wfile.write(json.dumps(body).encode())
        def do_POST(self):
            raise AssertionError('Discovery must never generate model output')
        def log_message(self, *args): pass
    api = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{api.server_port}', requests, state
    api.shutdown(); api.server_close()

@pytest.mark.parametrize('provider,suffix', [('anthropic',''), ('anthropic','/v1'), ('openai','/v1')])
def test_discovery_uses_unsaved_settings_without_persisting(http,tmp_path,monkeypatch,model_api,provider,suffix):
    monkeypatch.setattr(server,'ROOT',tmp_path)
    save_config(tmp_path, {'api_key':'saved-secret','model':'saved-model'})
    before=load_config(tmp_path)
    base,requests,state=model_api
    code,data=http('/__model_list__',{'provider':provider,'base_url':base+suffix,'api_key':'draft-secret','proxy_mode':'manual','proxy_url':'http://127.0.0.1:1'})
    assert code==200
    assert data=={'models':['a-model','z-model']}
    path,headers=requests[0]; headers={k.lower():v for k,v in headers.items()}
    assert path=='/v1/models'
    assert headers.get('x-api-key')=='draft-secret' if provider=='anthropic' else headers.get('authorization')=='Bearer draft-secret'
    if provider=='anthropic': assert headers['anthropic-version']=='2023-06-01'
    assert load_config(tmp_path)==before
    assert 'secret' not in json.dumps(data)

@pytest.mark.parametrize('status,body,expected',[(200,{'data':[]},200),(404,{'error':'secret'},422),(200,{},502),(200,{'data':[{'id':7}]},502),(401,{'error':'secret'},502)])
def test_discovery_empty_unsupported_and_errors(http,tmp_path,monkeypatch,model_api,status,body,expected):
    monkeypatch.setattr(server,'ROOT',tmp_path)
    base,requests,state=model_api; state.update(status=status,body=body)
    code,data=http('/__model_list__',{'base_url':base,'proxy_mode':'direct'})
    assert code==expected
    assert 'secret' not in json.dumps(data)
    if expected==200: assert data=={'models':[]}

def test_discovery_retains_saved_key_only_for_same_provider(http,tmp_path,monkeypatch,model_api):
    monkeypatch.setattr(server,'ROOT',tmp_path)
    save_config(tmp_path,{'api_key':'saved-secret'})
    base,requests,state=model_api
    assert http('/__model_list__',{'base_url':base,'api_key':''})[0]==200
    assert {k.lower():v for k,v in requests[-1][1].items()}['x-api-key']=='saved-secret'
    assert http('/__model_list__',{'provider':'openai','base_url':base+'/v1','api_key':''})[0]==200
    assert 'Authorization' not in requests[-1][1]
    assert http('/__model_list__',{'base_url':base,'clear_api_key':True})[0]==200
    assert {k.lower():v for k,v in requests[-1][1].items()}.get('x-api-key','')==''

@pytest.mark.parametrize('patch',[{'provider':'unknown'},{'base_url':'file:///secret'},{'proxy_mode':'manual','proxy_url':''},{'api_key':123},{'extra':True},[]])
def test_discovery_rejects_invalid_drafts_before_network(http,tmp_path,monkeypatch,patch):
    monkeypatch.setattr(server,'ROOT',tmp_path)
    assert http('/__model_list__',patch)[0]==400

def test_discovery_follows_anthropic_metadata_pages(http,tmp_path,monkeypatch,model_api):
    monkeypatch.setattr(server,'ROOT',tmp_path)
    base,requests,state=model_api
    state['body']=lambda path: {'data':[{'id':'second'}],'has_more':False} if 'after_id=' in path else {'data':[{'id':'first'}],'has_more':True,'last_id':'first'}
    assert http('/__model_list__',{'base_url':base})==(200,{'models':['first','second']})
    assert requests[-1][0]=='/v1/models?after_id=first'

def test_discovery_routes_remote_metadata_through_manual_proxy(http,tmp_path,monkeypatch,model_api):
    monkeypatch.setattr(server,'ROOT',tmp_path);monkeypatch.setenv('NO_PROXY','')
    base,requests,state=model_api
    assert http('/__model_list__',{'provider':'openai','base_url':'http://model.invalid/v1','proxy_mode':'manual','proxy_url':base})[0]==200
    assert requests[0][0]=='http://model.invalid/v1/models'
