import json
import pytest
from urllib.request import Request
from model_settings import load_config, save_config, public_config, proxy_info
from model_client import adapt_request, normalize_response

def test_settings_secret_preserved_and_not_public(tmp_path, monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    save_config(tmp_path, {'provider':'openai','model':'local-model','base_url':'http://localhost:11434/v1','api_key':'secret','proxy_mode':'direct'})
    save_config(tmp_path, {'model':'other','api_key':''})
    assert load_config(tmp_path)['api_key']=='secret'
    assert 'secret' not in json.dumps(public_config(tmp_path))
    assert public_config(tmp_path)['has_api_key']

@pytest.mark.parametrize('patch', [{'provider':'bad'},{'base_url':'file:///tmp/x'},{'proxy_mode':'bad'},{'proxy_url':'socks5://localhost:1'},{'model':''}])
def test_invalid_settings(tmp_path, patch):
    with pytest.raises(ValueError): save_config(tmp_path,patch)

def test_openai_tools_and_response(tmp_path):
    save_config(tmp_path,{'provider':'openai','model':'qwen','base_url':'http://localhost:11434/v1','proxy_mode':'direct'})
    body={'model':'claude','max_tokens':42,'system':'rules','messages':[{'role':'user','content':'hi'}], 'tools':[{'name':'retain','input_schema':{'type':'object'}}],'tool_choice':{'name':'retain'}}
    req=adapt_request(Request('https://old/v1/messages',data=json.dumps(body).encode()),load_config(tmp_path))
    sent=json.loads(req.data)
    assert req.full_url=='http://localhost:11434/v1/chat/completions'
    assert sent['model']=='qwen' and sent['messages'][0]=={'role':'system','content':'rules'}
    assert sent['tool_choice']['function']['name']=='retain'
    assert sent['parallel_tool_calls'] is False
    result=normalize_response({'choices':[{'finish_reason':'length','message':{'tool_calls':[{'function':{'name':'retain','arguments':'{"x":1}'}}]}}]},'openai')
    assert result['stop_reason']=='max_tokens'
    assert result['content'][0]['input']=={'x':1}

def test_proxy_modes(tmp_path, monkeypatch):
    monkeypatch.setenv('HTTPS_PROXY','http://127.0.0.1:7890')
    c=load_config(tmp_path)
    assert proxy_info(c)['source']=='environment'
    c['proxy_mode']='direct'
    assert proxy_info(c)['proxies']=={}
    c.update(proxy_mode='manual',proxy_url='http://localhost:8080')
    assert proxy_info(c)['proxies']['https']=='http://localhost:8080'
