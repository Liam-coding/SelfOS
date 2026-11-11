from tests.test_knowledge_settings_http import http
import serve

def test_model_http_private_settings_and_running_guard(http,tmp_path,monkeypatch):
    monkeypatch.setattr(serve,'ROOT',tmp_path)
    code,data=http('/__model_settings__')
    assert code==200 and data['provider']=='anthropic' and 'api_key' not in data
    code,data=http('/__model_settings__',{'model':'test-model','api_key':'secret'})
    assert code==200 and data['has_api_key'] and 'api_key' not in data
    serve.KNOWLEDGE_RUN['stop_file']=tmp_path/'stop'
    assert http('/__model_settings__',{'model':'other'})[0]==409
