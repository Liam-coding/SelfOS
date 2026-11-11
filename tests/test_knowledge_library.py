import json
from selfos.app import library as library_api
from pathlib import Path
import pytest


def library():

    return library_api


@pytest.fixture
def vault(tmp_path):
    state={'cards':{'alpha':{'project_id':'alpha','title':'Reliable Import','intent':'Recover interrupted jobs',
        'status':'blocked','decisions':['Use checkpoints'],'decision_history':['Old batch format','Use checkpoints'],
        'blockers':['Provider error'],'next_steps':['Validate retry'],'source_ids':['m1'],
        'updated_at':'2026-11-10T08:00:00Z','verified':False}},
        'lessons':[{'text':'Use atomic installation','kind':'inference','domain':'work','source_ids':['m1']}],
        'personal_facts':[{'key':'occupation','value':'Researcher','text':'Works as a researcher',
            'domain':'personal','kind':'user_fact','source_ids':['m1'],'evidence':'I work as a researcher.'}],
        'preferences':[{'key':'language','value':'Chinese','text':'Prefers Chinese explanations',
            'domain':'personal','kind':'user_fact','source_ids':['m1'],'evidence':'I prefer Chinese explanations.'}],
        'records_history':[{'key':'language','value':'English','text':'Previously preferred English',
            'kind':'user_fact','source_ids':['m1'],'original_category':'preferences'}],
        'sources':{'m1':{'path':'C:/private/conversations/session.jsonl','timestamp':'2026-11-10T08:00:00Z',
            'source':'codex','role':'user','provenance':'quoted_dialogue','session_id':'original','project_id':'alpha'}}}
    (tmp_path/'.knowledge_pipeline.json').write_text(json.dumps(state),encoding='utf-8')
    return tmp_path


def test_categories_and_history_are_distinct(vault):
    api=library()
    assert api.list_knowledge(vault,category='projects')['total']==1
    assert api.list_knowledge(vault,category='preferences')['items'][0]['summary']=='Prefers Chinese explanations'
    history=api.list_knowledge(vault,category='history')
    assert any('English' in r['summary'] for r in history['items'])
    assert any('Old batch format' in r['summary'] for r in history['items'])
    assert not any(r['summary']=='Use checkpoints' for r in history['items'])


def test_method_support_scope_is_available_without_claiming_verified_evidence(vault):
    path=vault/'.knowledge_pipeline.json';state=json.loads(path.read_text())
    state['lessons'][0].update(support_review='summary_model_review',source_scope='summary_context',verified=False)
    path.write_text(json.dumps(state),encoding='utf-8')
    row=library().list_knowledge(vault,category='lessons')['items'][0]
    assert row['support_review']=='summary_model_review' and row['verified'] is False
    detail=library().knowledge_detail(vault,row['id'])['item']
    assert detail['support_review']=='summary_model_review' and detail['kind']=='inference'


def test_unchanged_library_reuses_view_and_refreshes_after_write(vault,monkeypatch):
    api=library();calls=[];original=api._records
    def count(state):
        calls.append(True)
        return original(state)
    monkeypatch.setattr(api,'_records',count)
    first=api.list_knowledge(vault,category='projects')
    identity=first['items'][0]['id']
    api.knowledge_detail(vault,identity)
    assert len(calls)==1
    first['items'][0]['title']='Caller mutation'
    assert api.list_knowledge(vault,category='projects')['items'][0]['title']=='Reliable Import'
    path=vault/'.knowledge_pipeline.json';state=json.loads(path.read_text())
    state['cards']['alpha']['title']='Updated import'
    path.write_text(json.dumps(state),encoding='utf-8')
    assert api.list_knowledge(vault,category='projects')['items'][0]['title']=='Updated import'
    assert len(calls)==2


def test_search_matches_meaningful_content_and_paginates(vault):
    api=library()
    result=api.list_knowledge(vault,query='CHECKPOINTS',limit=1)
    assert result['total']==1 and result['items'][0]['category']=='projects'
    assert api.list_knowledge(vault,query='m1')['total']==0
    assert api.list_knowledge(vault,limit=2,offset=2)['total']>2


@pytest.mark.parametrize('kwargs',[{'category':'unknown'},{'limit':0},{'limit':201},{'offset':-1},{'query':'x'*501}])
def test_invalid_browse_parameters_are_rejected(vault,kwargs):
    with pytest.raises(ValueError):library().list_knowledge(vault,**kwargs)


def test_detail_has_evidence_provenance_without_absolute_source_paths(vault):
    api=library()
    row=api.list_knowledge(vault,category='preferences')['items'][0]
    detail=api.knowledge_detail(vault,row['id'])
    assert detail['item']['evidence']=='I prefer Chinese explanations.'
    assert detail['sources'][0]['provenance']=='quoted_dialogue'
    assert detail['sources'][0]['file']=='session.jsonl'
    assert 'C:/private' not in json.dumps(detail)
    with pytest.raises(KeyError):api.knowledge_detail(vault,'nonexistent')


def test_legacy_decision_history_has_no_invented_event_date(vault):
    api=library();row=api.list_knowledge(vault,category='history',query='Old batch format')['items'][0]
    assert row['date']==''
    assert api.knowledge_detail(vault,row['id'])['item']['source_scope']=='project_context'


def test_decision_history_uses_session_lineage(vault):
    path=vault/'.knowledge_pipeline.json';state=json.loads(path.read_text())
    state['cards']['alpha']['decision_records']=[{'text':'Old batch format','source_ids':['m1'],
        'observed_at':'2026-11-01T08:00:00Z','source_scope':'session_context'}]
    path.write_text(json.dumps(state),encoding='utf-8')
    row=library().list_knowledge(vault,category='history',query='Old batch format')['items'][0]
    assert row['date']=='2026-11-01T08:00:00Z'


def test_source_retrieval_requires_known_allowed_conversation_file(tmp_path,monkeypatch):
    from knowledge import extract_conversations
    api=library();sessions=tmp_path/'sessions';sessions.mkdir()
    path=sessions/'session.jsonl'
    path.write_text(json.dumps({'type':'user','timestamp':'2026-11-10T08:00:00Z','sessionId':'s1',
        'message':{'content':'I prefer Chinese explanations.'}}),encoding='utf-8')
    messages=extract_conversations([sessions]);message=messages[0]
    vault=tmp_path/'vault';vault.mkdir()
    (vault/'.knowledge_pipeline.json').write_text(json.dumps({'sources':{message['id']:message}}),encoding='utf-8')
    monkeypatch.setattr(api,'local_roots',lambda:[sessions])
    detail=api.knowledge_source(vault,message['id'])
    assert detail['text']==message['text'] and detail['role']=='user'
    with pytest.raises(KeyError):api.knowledge_source(vault,'../../private')
    monkeypatch.setattr(api,'local_roots',lambda:[tmp_path/'other'])
    with pytest.raises(ValueError,match='source'):api.knowledge_source(vault,message['id'])
