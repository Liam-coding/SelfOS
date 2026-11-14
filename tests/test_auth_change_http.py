from tests.test_auth_http import http
from tests.test_change_publication import publish
from tests.test_knowledge_corrections import state,record

def test_change_endpoints_require_login_and_bind_proof_to_session(http,tmp_path):
    request,auth=http
    for path in ('/__knowledge_changes__','/__knowledge_change__','/__knowledge_change_source__'):
        assert request(path)[0]==401
    auth.setup('synthetic changes password')
    cookie='selfos_session='+auth.login('synthetic changes password')
    other='selfos_session='+auth.login('synthetic changes password')
    vault=tmp_path/'app/vault';vault.mkdir(parents=True,exist_ok=True)
    publish(vault,state(record()))
    code,page,_=request('/__knowledge_changes__',cookie=cookie)
    assert code==200 and len(page['items'])==1
    query='/__knowledge_change__?id='+page['items'][0]['id']+'&cursor='+page['cursor']
    assert request(query,cookie=cookie)[1]['status']=='verified'
    assert request(query,cookie=other)[0]==400

def test_change_api_rejects_malformed_identity_without_snapshot(http):
    request,auth=http
    auth.setup('synthetic changes password')
    cookie='selfos_session='+auth.login('synthetic changes password')
    code,result,_=request('/__knowledge_change__?id=../outside',cookie=cookie)
    assert code==400 and not result.get('items')
