import selfos.web.server as _web_server
from tests.test_knowledge_settings_http import http


def test_model_http_private_settings_and_running_guard(http,tmp_path,monkeypatch):
    monkeypatch.setattr(_web_server,'ROOT',tmp_path)
    code,data=http('/__model_settings__')
    assert code==200 and data['provider']=='anthropic' and 'api_key' not in data
    code,data=http('/__model_settings__',{'model':'test-model','api_key':'secret'})
    assert code==200 and data['has_api_key'] and 'api_key' not in data
    _web_server.KNOWLEDGE_RUN['stop_file']=tmp_path/'stop'
    assert http('/__model_settings__',{'model':'other'})[0]==409
