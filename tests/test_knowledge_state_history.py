import copy
from knowledge_pipeline import merge_project_card
from knowledge_history import history_records
from tests.test_project_knowledge_contract import card


def test_previous_blocker_and_next_step_have_separate_sourced_history():
    old=card(status='blocked',blockers=['Missing mapping'],next_steps=['Repair mapping'],source_ids=['m1'])
    new=card(status='in_progress',blockers=[],next_steps=['Validate retries'],source_ids=['m2'],updated_at='2026-11-10T09:00:00Z')
    merged=merge_project_card(old,new)
    history=[r for r in history_records({'cards':{'alpha':merged}}) if r.get('original_category')=='project_state']
    assert merged['blockers']==[] and merged['next_steps']==['Validate retries']
    assert len(history)==1 and 'Missing mapping' in history[0]['text']
    assert 'Repair mapping' in history[0]['text']
    assert history[0]['source_ids']==['m1'] and history[0]['observed_at']==old['updated_at']
    assert history[0]['kind']=='inference' and not history[0]['verified']
    assert 'resolved' not in history[0]['text'].lower()


def test_out_of_order_state_history_keeps_every_distinct_snapshot():
    first=card(status='blocked',source_ids=['m1'])
    middle=card(status='paused',source_ids=['m2'],updated_at='2026-11-10T09:00:00Z')
    last=card(status='in_progress',blockers=[],source_ids=['m3'],updated_at='2026-11-10T10:00:00Z')
    result=merge_project_card(merge_project_card(first,last),middle)
    history=[r for r in history_records({'cards':{'alpha':result}}) if r.get('original_category')=='project_state']
    assert result['status']=='in_progress'
    assert {tuple(r['source_ids']) for r in history}=={('m1',),('m2',)}


def test_state_history_is_written_and_visible_with_its_original_source(tmp_path):
    from knowledge_pipeline import consolidate_sessions
    from knowledge_library import list_knowledge,knowledge_detail
    from tests.test_project_knowledge_contract import session
    first=session('Upload project is blocked on signature mapping.',identity='m1',session='s1')
    later=session('Signature mapping is fixed. Next validate replay.',identity='m2',session='s2',timestamp='2026-11-10T09:00:00Z')
    def generate(item):
        blocked=item['session_id']=='s1'
        return {'project':card(project_id=item['project_id'],source_ids=[item['messages'][0]['id']],
            updated_at=item['messages'][0]['timestamp'],status='blocked' if blocked else 'in_progress',
            blockers=['Signature mapping'] if blocked else [],
            next_steps=['Repair signature mapping'] if blocked else ['Validate replay']), 'lessons':[]}
    consolidate_sessions(tmp_path,[first,later],generate,max_workers=2)
    rows=list_knowledge(tmp_path,'history',query='Signature mapping')['items']
    assert len(rows)==1 and rows[0]['source_count']==1
    assert rows[0]['original_category']=='project_state'
    detail=knowledge_detail(tmp_path,rows[0]['id'])
    assert detail['item']['original_category']=='project_state'
    assert detail['item']['kind']=='inference' and not detail['item']['verified']
    assert detail['sources'][0]['id']=='m1'
    assert 'Earlier project state: blocked' in (tmp_path/'knowledge/history.md').read_text()


def test_repeated_state_does_not_pollute_history_or_mutate_input():
    first=card(source_ids=['m1'])
    later=card(source_ids=['m2'],updated_at='2026-11-10T09:00:00Z')
    original=copy.deepcopy(first)
    result=merge_project_card(first,later)
    assert first==original
    assert not [r for r in history_records({'cards':{'alpha':result}}) if r.get('original_category')=='project_state']
    assert result['state_records'][0]['source_ids']==['m1','m2']


def test_unknown_update_does_not_manufacture_a_state_event():
    old=card(status='blocked')
    new=card(status='unknown',updated_at='2026-11-10T09:00:00Z',source_ids=['m2'])
    result=merge_project_card(old,new)
    assert result['status']=='blocked'
    assert len(result['state_records'])==1


def test_late_arriving_pause_between_equal_states_preserves_original_episode():
    early=card(status='in_progress',source_ids=['m1'])
    late=card(status='in_progress',source_ids=['m3'],updated_at='2026-11-10T10:00:00Z')
    middle=card(status='paused',source_ids=['m2'],updated_at='2026-11-10T09:00:00Z')
    result=merge_project_card(merge_project_card(early,late),middle)
    history=[r for r in history_records({'cards':{'alpha':result}}) if r.get('original_category')=='project_state']
    assert [r['source_ids'] for r in history]==[['m1'],['m2']]
    assert result['status']=='in_progress'


def test_state_history_preserves_its_original_domain():
    old=card(domain='work',status='blocked',source_ids=['m1'])
    new=card(domain='research',status='in_progress',blockers=[],source_ids=['m2'],updated_at='2026-11-10T09:00:00Z')
    result=merge_project_card(old,new)
    history=[r for r in history_records({'cards':{'alpha':result}}) if r.get('original_category')=='project_state']
    assert history[0]['domain']=='work'
    assert result['domain']=='research'


def test_equal_states_in_different_domains_keep_separate_history():
    old=card(domain='work',source_ids=['m1'])
    new=card(domain='research',source_ids=['m2'],updated_at='2026-11-10T09:00:00Z')
    result=merge_project_card(old,new)
    history=[r for r in history_records({'cards':{'alpha':result}}) if r.get('original_category')=='project_state']
    assert len(history)==1 and history[0]['source_ids']==['m1']
    assert history[0]['domain']=='work'
