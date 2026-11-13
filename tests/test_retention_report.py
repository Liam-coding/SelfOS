import json
from selfos.app import quality_report as report


def save(vault, state):
    (vault / '.knowledge_pipeline.json').write_text(json.dumps(state), encoding='utf-8')


def test_legacy_zero_is_uncertain(tmp_path):
    save(tmp_path, {'cards': {}, 'lessons': []})
    data = report.quality_report(tmp_path)
    assert data['counts']['personal_facts'] == 0
    assert data['categories']['personal_facts']['explanation'] == 'unknown'


def test_category_review_and_consolidation_have_safe_source_examples(tmp_path):
    save(tmp_path, {'cards': {}, 'lessons': [], 'sources': {'s1': {'path': 'C:/private/source.jsonl'}},
        'retention_audit': [
            {'category': 'personal_facts', 'source_ids': ['s1'], 'reason': 'temporary_request'},
            {'stage': 'cross_batch_method_merge', 'source_ids': ['s1'], 'merge_applied': True,
             'reason': 'secret raw response C:/private/key.txt'}]})
    data = report.quality_report(tmp_path)
    assert data['stages']['category_review']['total'] == 1
    assert data['stages']['consolidation']['total'] == 1
    assert data['examples'][0]['source_ids'] == ['s1']
    assert 'C:/private' not in json.dumps(data)
    assert 'secret raw response' not in json.dumps(data)


def test_filtering_metadata_matches_compaction(tmp_path):
    from selfos.sources.compaction import prepare_sessions
    audit = {}
    messages = [{'id': 'a', 'role': 'user', 'text': 'retry', 'project_id': 'synthetic', 'session_id': 'one'},
                {'id': 'b', 'role': 'user', 'text': 'I work as a researcher', 'project_id': 'synthetic', 'session_id': 'one'}]
    sessions = prepare_sessions(messages, audit=audit)
    assert len(sessions) == 1
    assert audit['input_messages'] == 2
    assert audit['filtered_messages'] == 1
    assert audit['examples'][0]['reason'] == 'transient_content'


def test_unresolved_failure_blocks_zero_explanation_and_is_bounded(tmp_path):
    folder = tmp_path / '.knowledge_errors' / '20261113T120000-abcdefabcdef'
    folder.mkdir(parents=True)
    (folder / '000001-1.json').write_text(json.dumps({'error': 'Invalid evidence secret',
        'known_source_ids': ['s1'], 'response_redacted': 'DO NOT DISPLAY'}))
    save(tmp_path, {'cards': {}, 'lessons': [], 'sources': {'s1': {}}, 'quality_sessions': {
        'key': {'source_ids': ['s1'], 'categories': {'personal_facts': 0, 'preferences': 0}}}})
    data = report.quality_report(tmp_path)
    assert data['stages']['validation']['total'] == 1
    assert data['categories']['personal_facts']['explanation'] == 'unresolved'
    assert 'DO NOT DISPLAY' not in json.dumps(data)


def test_excluded_sources_suppress_diagnostic_examples(tmp_path):
    root = tmp_path / 'conversations'; root.mkdir()
    (tmp_path / '.knowledge_sources.json').write_text(json.dumps({'version': 1, 'roots': [str(root)], 'exclusions': [str(root)]}))
    save(tmp_path, {'cards': {}, 'lessons': [], 'sources': {'s1': {'path': str(root / 'a.jsonl')}},
        'retention_audit': [{'category': 'preferences', 'source_ids': ['s1'], 'reason': 'temporary_request'}]})
    assert report.quality_report(tmp_path)['examples'] == []


def test_real_extraction_zero_and_validation_repair_are_distinct(tmp_path):
    from selfos.app.pipeline import consolidate_sessions
    from tests.test_project_knowledge_contract import session
    item=session('I work as a researcher.')
    calls=[]
    def summarize(value):
        calls.append(value)
        if len(calls)==1: raise ValueError('Invalid evidence: private raw claim')
        return {'project':None,'lessons':[],'personal_facts':[],'preferences':[]}
    result=consolidate_sessions(tmp_path,[item],summarize,max_workers=1)
    assert result['completed_sessions']==1 and not result['failed_sessions']
    data=report.quality_report(tmp_path)
    assert data['categories']['personal_facts']['explanation']=='reviewed_zero'
    assert data['stages']['extraction']['total']==1
    assert data['stages']['validation']['total']==1
    assert any(e['reason']=='recovered_attempt' for e in data['examples'])


def test_real_misclassification_matches_current_backend_count(tmp_path):
    from selfos.app.pipeline import consolidate_sessions
    from tests.test_project_knowledge_contract import session
    item=session('For this project use Python.')
    def summarize(value):
        return {'project':None,'lessons':[],'personal_facts':[{'key':'language','value':'Python',
            'text':'Uses Python','domain':'work','kind':'user_fact','source_ids':['m1'],
            'evidence':'For this project use Python.','claim_type':'project_choice'}],'preferences':[]}
    result=consolidate_sessions(tmp_path,[item],summarize,max_workers=1)
    assert result['completed_sessions']==1
    data=report.quality_report(tmp_path)
    assert data['counts']['personal_facts']==0
    assert data['stages']['category_review']['total']==1
    assert any(e['reason']=='project_choice' for e in data['examples'])


def test_oversized_state_and_diagnostics_report_incompleteness(tmp_path,monkeypatch):
    save(tmp_path, {'cards': {},'lessons':[]})
    monkeypatch.setattr(report,'MAX_BYTES',1)
    data=report.quality_report(tmp_path)
    assert data['incomplete']
    assert data['categories']['preferences']['explanation']=='unknown'


def test_successful_fact_consolidation_has_exact_totals_and_sources(tmp_path):
    from selfos.app.pipeline import consolidate_sessions
    from tests.test_project_knowledge_contract import session
    def summarize(item):
        return {'project':None,'lessons':[],'personal_facts':[{'key':'occupation','value':'researcher',
            'text':'Works as researcher','domain':'work','kind':'user_fact',
            'source_ids':[item['messages'][0]['id']],'evidence':'I work as a researcher.'}],'preferences':[]}
    result=consolidate_sessions(tmp_path,[session('I work as a researcher.'),
        session('I work as a researcher.',identity='m2',session='s2')],summarize,max_workers=1)
    assert result['completed_sessions']==2
    data=report.quality_report(tmp_path)
    assert data['counts']['personal_facts']==1
    assert data['stages']['consolidation']['total']==1
    assert any(set(e['source_ids'])=={'m1','m2'} and e['reason']=='consolidated' for e in data['examples'])


def test_failed_staging_has_job_link_and_never_changes_canonical_totals(tmp_path):
    identity='20261113T120000-abcdefabcdef';checkpoint='a'*24
    folder=tmp_path/'.knowledge_jobs'/'operations';folder.mkdir(parents=True)
    (folder/(identity+'.json')).write_text(json.dumps({'id':identity,'status':'failed',
        'phase':'extracting','checkpoint':checkpoint}))
    diagnostics=tmp_path/'.knowledge_rebuild'/checkpoint/'.knowledge_errors'/'run'
    diagnostics.mkdir(parents=True)
    (diagnostics/'000001-1.json').write_text(json.dumps({'known_source_ids':['missing'],
        'response_redacted':'secret model response','error':'private text'}))
    save(tmp_path,{'cards':{},'lessons':[]})
    data=report.quality_report(tmp_path)
    assert data['counts']['personal_facts']==0
    assert data['categories']['personal_facts']['explanation']=='unresolved'
    assert data['jobs'][0]['id']==identity and not data['jobs'][0]['retryable']
    example=next(e for e in data['examples'] if e['stage']=='validation')
    assert example['job_id']==identity and example['source_ids']==['missing']
    assert example['source_available'] is False
    assert 'secret model' not in json.dumps(data)


def test_published_filtering_totals_are_exact(tmp_path):
    identity='20261113T120000-abcdefabcdef'
    folder=tmp_path/'.knowledge_jobs'/'operations';folder.mkdir(parents=True)
    (folder/(identity+'.json')).write_text(json.dumps({'id':identity,'status':'completed',
        'phase':'publishing','filtering':{'input_messages':3,'filtered_messages':2,
            'examples':[{'source_ids':['s1'],'reason':'transient_content'}]}}))
    save(tmp_path,{'cards':{},'lessons':[],'sources':{'s1':{}},'last_operation':{'id':identity}})
    data=report.quality_report(tmp_path)
    assert data['stages']['filtering']['total']==2
    assert data['stages']['filtering']['input_messages']==3
    assert any(e['reason']=='transient_content' for e in data['examples'])


def test_incomplete_metadata_never_implies_eligible_absence(tmp_path,monkeypatch):
    save(tmp_path,{'cards':{},'lessons':[],'quality_sessions':{'s':{'source_ids':[],
        'categories':{'preferences':0}}}})
    folder=tmp_path/'.knowledge_errors';folder.mkdir()
    for i in range(3):(folder/str(i)).mkdir()
    monkeypatch.setattr(report,'MAX_FILES',1)
    data=report.quality_report(tmp_path)
    assert data['incomplete']
    assert not data['eligible_absence_proven']


def test_timeout_has_actionable_safe_reason_without_error_prose(tmp_path):
    save(tmp_path,{'cards':{},'lessons':[],'sources':{'s1':{}}})
    folder=tmp_path/'.knowledge_errors'/'run';folder.mkdir(parents=True)
    (folder/'1.json').write_text(json.dumps({'error':'request timed out accessing C:/private/key',
        'known_source_ids':['s1']}))
    data=report.quality_report(tmp_path)
    assert data['examples'][0]['reason']=='request_timeout'
    assert 'private' not in json.dumps(data)


def test_user_deletion_explains_zero_and_respects_corrected_counts(tmp_path):
    from tests.test_knowledge_corrections import state,record,action
    data=state(record());ledger=action(data,{},'delete')
    save(tmp_path,data)
    (tmp_path/'.knowledge_corrections.json').write_text(json.dumps(ledger),encoding='utf-8')
    result=report.quality_report(tmp_path)
    assert result['counts']['preferences']==0
    assert result['categories']['preferences']['explanation']=='user_suppressed'
    assert any(e['reason']=='user_suppressed' for e in result['examples'])


def retry_fixture(vault, published=True, covered=True):
    checkpoint = 'b' * 24
    old = '20261113T120000-aaaaaaaaaaaa'
    new = '20261113T130000-bbbbbbbbbbbb'
    folder = vault / '.knowledge_jobs' / 'operations'
    folder.mkdir(parents=True)
    for identity, status in ((old, 'failed'), (new, 'completed' if published else 'failed')):
        (folder / (identity + '.json')).write_text(json.dumps(dict(
            id=identity, status=status, phase='extracting', checkpoint=checkpoint)))
    errors = vault / '.knowledge_rebuild' / checkpoint / '.knowledge_errors' / 'old-run'
    errors.mkdir(parents=True)
    (errors / '000001-1.json').write_text(json.dumps(dict(known_source_ids=['s1'], error='Invalid evidence')))
    save(vault, dict(cards={}, lessons=[], sources={'s1': {}},
        last_operation={'id': new} if published else {}, quality_sessions={
            'part': dict(run_id='new-run', source_ids=['s1'] if covered else ['other'],
                categories={'personal_facts': 0, 'preferences': 0})}))
    return old, new


def test_shared_retry_checkpoint_counts_each_diagnostic_once(tmp_path):
    retry_fixture(tmp_path, published=False)
    data = report.quality_report(tmp_path)
    assert data['stages']['validation']['total'] == 1
    assert len([e for e in data['examples'] if e['stage'] == 'validation']) == 1


def test_published_retry_resolves_prior_failed_operation_and_diagnostic(tmp_path):
    old, new = retry_fixture(tmp_path)
    data = report.quality_report(tmp_path)
    assert data['categories']['personal_facts']['explanation'] == 'reviewed_zero'
    assert not next(job for job in data['jobs'] if job['id'] == old)['retryable']
    diagnostic = next(e for e in data['examples'] if e['stage'] == 'validation')
    assert diagnostic['reason'] == 'recovered_attempt'
    assert diagnostic['job_id'] == new


def test_publication_does_not_recover_uncovered_sources(tmp_path):
    retry_fixture(tmp_path, covered=False)
    data = report.quality_report(tmp_path)
    assert data['categories']['personal_facts']['explanation'] == 'unresolved'


def test_successful_refinement_retry_records_recovery_separately_from_extraction(tmp_path):
    from selfos.app.pipeline import consolidate_sessions, refine_projects
    from tests.test_project_knowledge_contract import session, summary
    consolidate_sessions(tmp_path, [session()], summary, max_workers=1)
    calls = []
    def refine(payload):
        calls.append(payload)
        if len(calls) == 1:
            raise ValueError('Invalid JSON during synthesis')
        return dict(project=payload['project'], lessons=[])
    result = refine_projects(tmp_path, refine)
    assert result['projects'] == 1
    data = report.quality_report(tmp_path)
    assert data['categories']['preferences']['explanation'] == 'reviewed_zero'
    assert next(e for e in data['examples'] if e['stage'] == 'validation')['reason'] == 'recovered_attempt'


def test_successful_review_retry_is_distinct_from_failed_refinement(tmp_path):
    from selfos.app.pipeline import consolidate_sessions, refine_projects
    from tests.test_project_knowledge_contract import session, summary
    consolidate_sessions(tmp_path, [session()], summary, max_workers=1)
    def refine(payload):
        return dict(project=payload['project'], lessons=[], _lesson_review_errors=[
            dict(batch_start=0, attempt=1, error='Invalid routing JSON', raw_response='synthetic')])
    refine_projects(tmp_path, refine)
    data = report.quality_report(tmp_path)
    assert data['categories']['preferences']['explanation'] == 'reviewed_zero'
    assert next(e for e in data['examples'] if e['stage'] == 'validation')['reason'] == 'recovered_attempt'


def test_report_retry_eligibility_matches_import_center(tmp_path):
    import hashlib
    from selfos.app.import_status import publication_status
    from selfos.knowledge.settings import DEFAULT_SETTINGS, policy_hash
    old, _ = retry_fixture(tmp_path, published=False)
    operations = tmp_path / '.knowledge_jobs' / 'operations'
    checkpoint = 'b' * 24
    staged = tmp_path / '.knowledge_rebuild' / checkpoint / '.knowledge_pipeline.json'
    staged.write_text(json.dumps(dict(cards={}, lessons=[], policy=DEFAULT_SETTINGS)))
    canonical = json.loads((tmp_path / '.knowledge_pipeline.json').read_text())
    expected = hashlib.sha256((tmp_path / '.knowledge_pipeline.json').read_bytes()).hexdigest()
    for path in operations.glob('*.json'):
        value = json.loads(path.read_text())
        value.update(expected_hash=expected, policy_hash=policy_hash(DEFAULT_SETTINGS))
        path.write_text(json.dumps(value))
    for compatible in (True, False):
        if not compatible:
            value = json.loads((operations / (old + '.json')).read_text())
            value['expected_hash'] = 'obsolete'
            (operations / (old + '.json')).write_text(json.dumps(value))
        reported = next(j for j in report.quality_report(tmp_path)['jobs'] if j['id'] == old)
        existing = next(j for j in publication_status(tmp_path, canonical, DEFAULT_SETTINGS)['operations'] if j['id'] == old)
        assert reported['retryable'] == existing['resume_eligible'] == compatible


def test_later_refinement_preserves_historical_recovery_evidence(tmp_path):
    from selfos.app.pipeline import consolidate_sessions, refine_projects
    from tests.test_project_knowledge_contract import session, summary
    consolidate_sessions(tmp_path, [session()], summary, max_workers=1)
    calls = 0
    def refine(payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError('Invalid JSON during synthesis')
        return dict(project=payload['project'], lessons=[], _lesson_review_errors=[
            dict(batch_start=0, attempt=1, error='Invalid routing JSON', raw_response='synthetic')] if calls == 2 else [])
    refine_projects(tmp_path, refine)
    assert report.quality_report(tmp_path)['categories']['preferences']['explanation'] == 'reviewed_zero'
    state = json.loads((tmp_path / '.knowledge_pipeline.json').read_text(encoding='utf-8'))
    state['refined'] = {}
    save(tmp_path, state)
    refine_projects(tmp_path, refine)
    data = report.quality_report(tmp_path)
    assert data['categories']['preferences']['explanation'] == 'reviewed_zero'
    assert all(e['reason'] == 'recovered_attempt' for e in data['examples'] if e['stage'] == 'validation')
