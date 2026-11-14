"""Deterministic question retrieval over synthetic retained record projections."""
from selfos.knowledge.identity import digest


def record(category, title, text, *, project='alpha', status='', date='2026-11-15T08:00:00Z', decisions=None):
    identity = digest([category, title, text, date])
    row = dict(id=identity, category=category, title=title, summary=text, date=date,
               kind='user_fact' if category in ('preferences', 'personal_facts') else 'inference',
               status=status, source_scope='record', verified=False, source_count=1,
               project_contexts=[{'id': project, 'title': 'Synthetic project', 'title_known': True}],
               domain='work')
    detail = dict(**row, evidence=text, user_corrected=False, conflict=False,
                  decisions=decisions or [], blockers=[], next_steps=[], supporting_source_ids=['s1'])
    sources = [dict(id='s1', file='synthetic.jsonl', source='codex', role='user', timestamp=date)]
    return row, detail, sources, text.casefold()


def test_natural_english_question_retrieves_decision_not_every_record():
    from selfos.knowledge.qa_retrieval import retrieve_records
    rows = [record('projects', 'Synthetic importer', 'Store local knowledge offline', status='in_progress',
                   decisions=['Use SQLite for atomic local transactions']),
            record('preferences', 'Editor preference', 'Prefer Python examples'),
            record('history', 'Legacy storage', 'Previously used JSON files')]
    result = retrieve_records(rows, 'Why did we choose SQLite?')
    assert [r['record']['title'] for r in result] == ['Synthetic importer']
    assert 'SQLite' in result[0]['text']


def test_current_overview_does_not_call_completed_projects_active():
    from selfos.knowledge.qa_retrieval import retrieve_records
    rows = [record('projects', 'Current project', 'Build source navigation', status='in_progress'),
            record('projects', 'Finished project', 'Completed a synthetic experiment', status='completed'),
            record('projects', 'Unknown project', 'Unconfirmed work', status='')]
    result = retrieve_records(rows, 'What am I working on?')
    assert [r['record']['title'] for r in result] == ['Current project']


def test_chinese_question_scaffolding_keeps_relevant_content():
    from selfos.knowledge.qa_retrieval import retrieve_records
    rows = [record('projects', '知识整理', '构建可以恢复的导入流程', status='blocked',
                   decisions=['使用 SQLite 保证原子写入']),
            record('lessons', '测试经验', '先用合成数据验证错误恢复')]
    assert [r['record']['title'] for r in retrieve_records(rows, '为什么我们选择 SQLite？')] == ['知识整理']
    assert [r['record']['title'] for r in retrieve_records(rows, '我现在在做什么？')] == ['知识整理']


def test_chinese_only_keywords_retrieve_relevant_experience():
    from selfos.knowledge.qa_retrieval import retrieve_records
    rows = [record('lessons', '写入经验', '原子写入可以避免中断后的数据不一致'),
            record('lessons', '测试经验', '使用合成数据验证恢复流程')]
    result = retrieve_records(rows, '为什么要原子写入？')
    assert [r['record']['title'] for r in result] == ['写入经验']


def test_unsupported_specific_question_does_not_fall_back_to_personal_facts():
    from selfos.knowledge.qa_retrieval import retrieve_records
    rows = [record('personal_facts', 'Occupation', 'Works as a synthetic researcher'),
            record('preferences', 'Explanations', 'Prefers short technical explanations')]
    assert retrieve_records(rows, 'What is my blood type?') == []
    assert retrieve_records(rows, 'What are my preferences about scuba diving?') == []
    assert retrieve_records(rows, '我的血型是什么？') == []


def test_preferences_and_explicit_history_are_distinguished():
    from selfos.knowledge.qa_retrieval import retrieve_records
    rows = [record('preferences', 'Current language', 'Prefers English explanations'),
            record('history', 'Old language', 'Previously preferred Chinese explanations')]
    current = retrieve_records(rows, 'What are my preferences?')
    assert [r['record']['category'] for r in current] == ['preferences']
    old = retrieve_records(rows, 'What language did I previously prefer?')
    assert any(r['historical'] and r['record']['category'] == 'history' for r in old)


def test_explicit_project_scope_never_borrows_other_project():
    from selfos.knowledge.qa_retrieval import retrieve_records
    rows = [record('projects', 'Alpha', 'Use SQLite for alpha', project='alpha', status='active'),
            record('projects', 'Beta', 'Use SQLite for beta', project='beta', status='active')]
    assert [r['record']['title'] for r in retrieve_records(rows, 'Why SQLite?', project='beta')] == ['Beta']
    assert retrieve_records(rows, 'Why SQLite?', project='unknown') == []


def test_projection_caps_text_records_and_representative_sources():
    from selfos.knowledge.qa_retrieval import retrieve_records
    rows = [record('projects', f'Synthetic SQLite {n}', 'SQLite ' * 2000, status='active') for n in range(20)]
    for _, detail, sources, _ in rows:
        sources.extend(dict(sources[0], id=f's{n}') for n in range(2, 30))
        detail['source_count'] = 29
    result = retrieve_records(rows, 'SQLite')
    assert 0 < len(result) <= 8
    assert sum(len(row['text']) for row in result) <= 12000
    assert sum(len(row['sources']) for row in result) <= 24
    assert all(row['source_count'] == 29 for row in result)
    assert all(row['source_coverage'] == 'representative' for row in result)
