import copy
from selfos.knowledge.projects import merge_project_card
from selfos.knowledge.history import history_records
from tests.test_project_knowledge_contract import card


def decisions(result):
    return [r for r in history_records({'cards':{'alpha':result}})
            if r.get('original_category')=='projects']


def test_previous_decision_keeps_its_domain_and_source():
    old=card(domain='work',decisions=['Use incremental import'],source_ids=['m1'])
    new=card(domain='research',decisions=['Evaluate alternatives'],source_ids=['m2'],updated_at='2026-11-10T09:00:00Z')
    before=copy.deepcopy(old)
    result=merge_project_card(old,new,limit=1)
    rows=decisions(result)
    assert len(rows)==1 and rows[0]['domain']=='work'
    assert rows[0]['source_ids']==['m1']
    assert rows[0]['observed_at']==old['updated_at']
    assert rows[0]['source_scope']=='session_context'
    assert old==before


def test_equal_decisions_in_different_domains_keep_separate_lineage():
    old=card(domain='work',source_ids=['m1'])
    new=card(domain='research',source_ids=['m2'],updated_at='2026-11-10T09:00:00Z')
    result=merge_project_card(old,new)
    assert len(result['decision_records'])==2
    rows=decisions(result)
    assert len(rows)==1 and rows[0]['domain']=='work'
    assert rows[0]['source_ids']==['m1']


def test_legacy_decision_without_domain_stays_unclassified():
    legacy=card(domain='research',decisions=['Current choice'],
        decision_history=['Earlier choice','Current choice'],
        decision_records=[{'text':'Earlier choice','source_ids':['m1'],
                          'observed_at':'2026-11-10T08:00:00Z','source_scope':'session_context'}])
    rows=decisions(legacy)
    assert len(rows)==1 and rows[0]['domain']=='unclassified'
    assert rows[0]['source_ids']==['m1']


def test_browser_can_open_equal_records_in_distinct_domains(tmp_path):
    import json
    from selfos.app.library import list_knowledge, knowledge_detail
    records=[{'text':'Use incremental import','source_ids':['m1'],
              'kind':'inference','domain':domain} for domain in ('work','research')]
    (tmp_path/'.knowledge_pipeline.json').write_text(json.dumps({'lessons':records}),encoding='utf-8')
    rows=list_knowledge(tmp_path,'lessons')['items']
    assert len({row['id'] for row in rows})==2
    assert {knowledge_detail(tmp_path,row['id'])['item']['domain'] for row in rows}=={'work','research'}
