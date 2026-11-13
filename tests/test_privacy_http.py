import selfos.web.server as server
from tests.test_knowledge_settings_http import http


def test_privacy_routes_roundtrip_and_active_import_guard(http,tmp_path,monkeypatch):
    monkeypatch.setattr(server,'ROOT',tmp_path)
    source=tmp_path/'sources';source.mkdir()
    selection={'roots':[str(source)],'exclusions':[],'privacy_exclusions':[str(tmp_path/'private-project')]}
    assert http('/__privacy__',{'action':'save','selection':selection})[0]==200
    code,status=http('/__privacy__')
    assert code==200 and status['selection']=={'version':1,**selection}
    assert 'api_key' not in status['destination']
    code,package=http('/__privacy__',{'action':'export'})
    assert code==200 and package['includes']['credentials'] is False
    server.KNOWLEDGE_RUN['stop_file']=tmp_path/'stop'
    assert http('/__privacy__',{'action':'save','selection':selection})[0]==409
    assert http('/__privacy__',{'action':'import','package':package})[0]==409
