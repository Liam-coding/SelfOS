"""Single-pass extraction and scoped preference publication contracts."""
import copy
import json
import threading
from pathlib import Path

import pytest

from tests.test_knowledge_evidence_protocol import response, record
from tests.test_project_knowledge_contract import session
from selfos.providers.knowledge import api_summarizer
from selfos.knowledge.evidence import output_schema
from selfos.knowledge.projects import validate_summary
from selfos.app.library import list_knowledge, knowledge_detail
from selfos.storage.records import managed_content


def test_default_extraction_is_one_call_and_locally_validated(monkeypatch):
    _, calls = response(monkeypatch, record(scope={'type':'global','id':''}))
    value = api_summarizer(Path('.'))(session('I prefer Chinese explanations.'))
    assert len(calls) == 1
    assert value['preferences'][0]['scope_type'] == 'global'
    assert value['preferences'][0]['source_ids'] == ['m1']
    assert not value.get('_additional_api_calls')


def test_public_adapter_defaults_to_single_pass(monkeypatch):
    _, calls = response(monkeypatch, record())
    from selfos.app.pipeline_api import api_summarizer as adapter
    adapter(Path('.'))(session('I prefer Chinese explanations.'))
    assert len(calls) == 1


def test_one_model_response_retains_project_and_all_record_categories(monkeypatch):
    from tests.test_project_knowledge_contract import summary
    from selfos.providers import knowledge, client
    item = session('I work as a researcher. I prefer concise explanations. We are building a search tool.')
    payload = summary(item)
    payload['project']['project_id']='current-project'
    payload['project']['source_ids']=['s1']
    payload.update(personal_facts=[record(key='work.role',value='researcher')],
                   preferences=[record(scope={'type':'activity','id':'learning'})],
                   history=[record(key='project.previous_choice',temporal='historical')],
                   lessons=[{'text':'Keep source links when consolidating records.', 'domain':'work',
                             'kind':'inference','source_ids':['s1']}])
    calls=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return json.dumps({'content':[{'type':'tool_use','name':'retain_knowledge','input':payload}]}).encode()
    def request(req,**kwargs):
        calls.append(req)
        return Response()
    monkeypatch.setattr(client,'request_opener',lambda root:request)
    monkeypatch.setattr(knowledge,'_get_api_config',lambda root:('test-key','https://example.test'))
    result=api_summarizer(Path('.'))(item)
    assert len(calls)==1
    assert result['project']['project_id']==item['project_id']
    for category in ('lessons','personal_facts','preferences','history'):
        assert len(result[category])==1
        assert result[category][0]['source_ids']==['m1']


def test_preference_and_fact_schemas_have_typed_scope():
    schema = output_schema({'m1':'s1'}, {'s1:e1':('m1','quote')}, 8)
    preference = schema['properties']['preferences']['items']
    assert 'scope' in preference['required']
    assert preference['properties']['scope']['properties']['type']['enum'] == ['global','activity','project','unknown']
    assert 'scope' in schema['properties']['personal_facts']['items']['required']


def test_project_alias_resolved_and_invalid_scope_rejected_in_default_path(monkeypatch):
    _, calls = response(monkeypatch, record(scope={'type':'project','id':'current-project'}))
    item = session('I prefer Chinese explanations in this project.')
    result = api_summarizer(Path('.'))(item)
    assert result['preferences'][0]['scope'] == item['project_id']
    assert validate_summary(result,item)['preferences'][0]['scope'] == item['project_id']
    response(monkeypatch, record(scope={'type':'project','id':'other-project'}))
    with pytest.raises(ValueError, match='scope'):
        api_summarizer(Path('.'))(item)


def test_publication_keeps_distinct_scope_identities_and_details(tmp_path):
    item = session('I prefer Chinese explanations.')
    raw = record(source_ids=['m1'], evidence=item['messages'][0]['text'])
    raw.pop('evidence_id')
    records = []
    for scope in ('work', 'learning'):
        records.append(validate_summary({'project':None,'lessons':[], 'preferences':[{**raw,'scope':scope}]},item)['preferences'][0])
    records[0].update(conflict=True, conflict_source_ids=['m1'])
    state = {'preferences':records, 'sources':{'m1':item['messages'][0]}}
    (tmp_path/'.knowledge_pipeline.json').write_text(json.dumps(state), encoding='utf-8')
    rows = list_knowledge(tmp_path, category='preferences')['items']
    assert len({row['id'] for row in rows}) == 2
    assert {row['scope'] for row in rows} == {'work','learning'}
    details = [knowledge_detail(tmp_path, row['id'])['item'] for row in rows]
    assert {detail['scope_type'] for detail in details} == {'activity'}
    markdown = managed_content('Personal note', 'Preferences', records, 'preferences').decode()
    assert 'Personal note' in markdown
    assert 'Scope: activity:work' in markdown
    assert 'Scope: activity:learning' in markdown


def test_scoped_preferences_survive_stop_resume_and_backup(tmp_path):
    from selfos.app.pipeline import consolidate_sessions
    from selfos.storage.pipeline import restore_pipeline_backup
    stop = threading.Event()
    items = [session('I prefer concise work explanations.', identity='m1'),
             session('I prefer detailed learning explanations.', identity='m2', session='s2')]
    def generate(item):
        identity = item['messages'][0]['id']
        scope = 'work' if identity=='m1' else 'learning'
        raw = record(scope={'type':'activity','id':scope}, value=scope,
                     source_ids=[identity], evidence=item['messages'][0]['text'])
        raw.pop('evidence_id')
        return {'project':None,'lessons':[], 'preferences':[raw]}
    def first(item):
        stop.set()
        return generate(item)
    initial = consolidate_sessions(tmp_path, items, first, max_workers=1, cancel=stop.is_set)
    assert initial['cancelled'] and initial['model_calls']==1
    resumed = consolidate_sessions(tmp_path, items, generate, max_workers=1)
    assert resumed['model_calls']==1
    rows = list_knowledge(tmp_path, category='preferences')['items']
    assert {row['scope'] for row in rows}=={'work','learning'}
    restore_pipeline_backup(tmp_path,resumed['run_id'])
    assert list_knowledge(tmp_path,category='preferences')['total']==1


@pytest.mark.parametrize('scope,kind',[('global','global'),('work','activity')])
def test_legacy_declared_scope_is_consistent_in_listing_and_detail(tmp_path,scope,kind):
    raw=record(scope=scope,source_ids=['m1'],evidence='I prefer Chinese explanations.')
    (tmp_path/'.knowledge_pipeline.json').write_text(json.dumps({'preferences':[raw]}),encoding='utf-8')
    row=list_knowledge(tmp_path,category='preferences')['items'][0]
    assert row['scope_type']==kind
    assert knowledge_detail(tmp_path,row['id'])['item']['scope_type']==kind


def test_project_alias_migrates_preference_scopes_and_cached_summaries(tmp_path):
    from selfos.app.pipeline import register_project_aliases
    from selfos.knowledge.records import validate_record
    item=session('I prefer Chinese explanations in this project.')
    origin=item['project_id'];target='C:/projects/canonical'
    raw=record(scope={'type':'project','id':'current-project'},source_ids=['m1'],evidence=item['messages'][0]['text'])
    pref=validate_record(raw,item)
    saved={'project':None,'lessons':[], 'preferences':[copy.deepcopy(pref)]}
    state={'cards':{},'sources':{'m1':item['messages'][0]},'preferences':[pref],
           'records_history':[{**pref,'original_category':'preferences','temporal':'historical'}],
           'summaries':{'saved':saved}}
    (tmp_path/'.knowledge_pipeline.json').write_text(json.dumps(state),encoding='utf-8')
    register_project_aliases(tmp_path,{origin:target})
    updated=json.loads((tmp_path/'.knowledge_pipeline.json').read_text(encoding='utf-8'))
    assert updated['preferences'][0]['scope']==target
    assert updated['records_history'][0]['scope']==target
    assert updated['summaries']['saved']['preferences'][0]['scope']==target
    migrated={**item,'project_id':target,'messages':[updated['sources']['m1']]}
    assert validate_summary(updated['summaries']['saved'],migrated)['preferences'][0]['scope']==target
    assert updated['sources']['m1']['path']==item['messages'][0]['path']
