import json

import pytest

from selfos.app.library import list_knowledge, knowledge_detail
from tests.test_knowledge_library import vault


def update(vault, change):
    path = vault / '.knowledge_pipeline.json'
    state = json.loads(path.read_text(encoding='utf-8'))
    change(state)
    path.write_text(json.dumps(state), encoding='utf-8')


def test_global_terms_match_across_fields_and_rank_title_first(vault):
    update(vault, lambda state: state['lessons'].append({
        'text': 'Reliable import needs atomic installation', 'kind': 'inference', 'source_ids': ['m1']}))
    result = list_knowledge(vault, query='reliable import')
    assert result['total'] == 7  # Project-context matches include its sourced records.
    assert result['items'][0]['category'] == 'projects'
    result = list_knowledge(vault, query='installation atomic')
    assert result['total'] == 2
    assert all('atomic installation' in row['match_excerpt'] for row in result['items'])
    assert all(row['match_ranges'] for row in result['items'])


def test_evidence_only_match_returns_actual_quote_not_unrelated_summary(vault):
    update(vault, lambda state: state['personal_facts'][0].update(
        evidence='I work as a researcher studying reproducibility.'))
    row = list_knowledge(vault, query='reproducibility')['items'][0]
    assert row['category'] == 'personal_facts'
    assert row['match_field'] == 'evidence'
    assert 'reproducibility' in row['match_excerpt']
    assert knowledge_detail(vault, row['id'])['item']['evidence'].endswith('reproducibility.')


def test_project_and_source_filters_use_provenance_context_across_categories(vault):
    base = list_knowledge(vault)
    project = next(item['id'] for item in base['filters']['projects'] if item['title'] == 'Reliable Import')
    result = list_knowledge(vault, project=project, source='codex')
    assert {'projects', 'lessons', 'personal_facts', 'preferences', 'history'} == {row['category'] for row in result['items']}
    assert all(row['project_contexts'][0]['id'] == project for row in result['items'])
    assert result['filtered_counts']['preferences'] == 1
    assert list_knowledge(vault, source='claude')['total'] == 0
    assert 'C:/private' not in json.dumps(result)


def test_date_range_is_inclusive_and_preserves_unknown_history(vault):
    result = list_knowledge(vault, date_from='2026-11-10', date_to='2026-11-10')
    assert result['total'] == 5
    assert all(row['date'].startswith('2026-11-10') for row in result['items'])
    assert list_knowledge(vault, category='history', query='Old batch format')['items'][0]['date'] == ''
    assert list_knowledge(vault, date_from='2026-11-11')['total'] == 0


def test_facets_are_query_filtered_but_not_hidden_by_selected_category(vault):
    result = list_knowledge(vault, category='preferences', query='Chinese')
    assert result['total'] == 1
    assert result['filtered_counts']['preferences'] == 1
    assert result['counts']['cards'] == 1
    assert result['filters']['projects']


def test_stable_pagination_and_redacted_matching(vault):
    update(vault, lambda state: state['lessons'].append({
        'text': 'Save api_key=privatevalue for diagnostics', 'kind': 'inference', 'source_ids': ['m1']}))
    assert list_knowledge(vault, query='privatevalue')['total'] == 0
    result = list_knowledge(vault, query='diagnostics')
    assert '[REDACTED]' in result['items'][0]['match_excerpt']
    first = list_knowledge(vault, limit=2)
    second = list_knowledge(vault, limit=2, offset=2)
    assert not {row['id'] for row in first['items']} & {row['id'] for row in second['items']}
    assert list_knowledge(vault, limit=2)['items'] == first['items']


def test_missing_source_metadata_does_not_hide_the_record(vault):
    update(vault, lambda state: state['sources'].update(m1=None))
    row = list_knowledge(vault, category='preferences')['items'][0]
    assert row['source_count'] == 0 and row['missing_source_count'] == 1
    assert knowledge_detail(vault, row['id'])['sources'] == []


def test_opaque_unknown_project_tokens_are_not_searchable_content(vault):
    def missing_project(state):
        state['cards'] = {}
        state['sources']['m1']['project_id'] = 'missing-project'
    update(vault, missing_project)
    context = list_knowledge(vault)['filters']['projects'][0]
    assert list_knowledge(vault, query=context['id'][:8])['total'] == 0


def test_cross_project_missing_title_is_not_borrowed_from_another_project(vault):
    def cross_project(state):
        state['sources']['m1']['project_id'] = 'beta'
        state['lessons'][0].update(project_id='alpha', project_title='Reliable Import')
    update(vault, cross_project)
    row = list_knowledge(vault, category='lessons')['items'][0]
    assert sum(context['title_known'] for context in row['project_contexts']) == 1
    assert len({context['title'] for context in row['project_contexts']}) == 2


def test_known_project_title_wins_over_unknown_metadata_for_same_identity(vault):
    def known_title(state):
        state['cards'] = {}
        state['lessons'].append({'project_id': 'alpha', 'project_title': 'Alpha',
            'text': 'Known project context', 'observed_at': '2026-11-11', 'source_ids': ['m1']})
    update(vault, known_title)
    context = list_knowledge(vault)['filters']['projects'][0]
    assert context['title'] == 'Alpha' and context['title_known']
    assert list_knowledge(vault, query='Alpha')['total'] == 5


def test_registered_project_aliases_do_not_create_duplicate_context_filters(vault):
    def aliases(state):
        state['cards']['beta'] = state['cards'].pop('alpha')
        state['cards']['beta']['project_id'] = 'beta'
        state['sources']['m1']['project_id'] = 'beta'
        state['project_aliases'] = {'alpha': 'beta'}
        state['lessons'][0]['project_id'] = 'alpha'
    update(vault, aliases)
    assert len(list_knowledge(vault)['filters']['projects']) == 1


@pytest.mark.parametrize('kwargs', [
    {'date_from': '2026-02-30'}, {'date_to': '20261110'},
    {'date_from': '2026-11-11', 'date_to': '2026-11-10'},
    {'project': []}, {'source': 'x' * 81}, {'date_from': None},
    {'query': ' '.join('term' + str(i) for i in range(21))},
])
def test_invalid_search_filters_are_rejected(vault, kwargs):
    with pytest.raises(ValueError):
        list_knowledge(vault, **kwargs)
