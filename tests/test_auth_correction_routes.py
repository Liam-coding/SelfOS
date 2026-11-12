import json
from tests.test_auth_http import http
from tests.test_knowledge_corrections import record, state


def test_correction_api_requires_login_and_applies_edit(http,tmp_path):
    request,auth=http
    assert request('/__knowledge_correct__',{'action':'edit'})[0]==401
    auth.setup('synthetic correction password')
    cookie='selfos_session='+auth.login('synthetic correction password')
    vault=tmp_path/'app/vault';vault.mkdir(parents=True,exist_ok=True)
    (vault/'.knowledge_pipeline.json').write_text(json.dumps(state(record())))
    _,listing,_=request('/__knowledge__?category=preferences',cookie=cookie)
    payload=dict(action='edit',ids=[listing['items'][0]['id']],patch={'value':'balanced','text':'Balanced explanations'})
    code,result,_=request('/__knowledge_correct__',payload,cookie)
    assert code==200 and result['action_id']
    assert request('/__knowledge__?category=preferences',cookie=cookie)[1]['items'][0]['title']=='balanced'
    assert request('/__knowledge_correct__',payload,cookie)[0]==409
    assert request('/__knowledge_correct__',{'action':'undo','action_id':result['action_id']},cookie)[0]==200


def test_correction_api_blocks_active_import_before_writing(http,tmp_path,monkeypatch):
    import selfos.web.server as server
    request,auth=http
    auth.setup('synthetic correction password')
    cookie='selfos_session='+auth.login('synthetic correction password')
    monkeypatch.setitem(server.KNOWLEDGE_RUN,'stop_file',tmp_path/'stop')
    assert request('/__knowledge_correct__',dict(action='delete',ids=['missing']),cookie)[0]==409
    assert not (tmp_path/'app/vault/.knowledge_corrections.json').exists()
