"""Grounded QA uses retained synthetic knowledge, not a new conversation scan."""
import json
from pathlib import Path

import pytest


@pytest.fixture
def qa_vault(tmp_path):
    from selfos.sources.selection import save_sources
    from tests.test_knowledge_corrections import record as preference
    vault = tmp_path / 'vault'
    source_root = tmp_path / 'synthetic-conversations'
    source_root.mkdir()
    source = source_root / 'synthetic.jsonl'
    source.write_text('Synthetic retained evidence only.', encoding='utf-8')
    save_sources(vault, {'roots': [str(source_root)], 'exclusions': []})
    state = dict(cards={'alpha': dict(project_id='alpha', title='Synthetic importer',
        intent='Recover local knowledge imports', status='in_progress', verified=False,
        decisions=['Use SQLite for atomic local writes'], blockers=[], next_steps=['Test recovery'],
        source_ids=['m1'], updated_at='2026-01-01T10:00:00Z')},
        preferences=[preference()], personal_facts=[], lessons=[], cache={},
        sources={'m1': dict(id='m1', path=str(source), source='codex', role='user',
            timestamp='2026-01-01T10:00:00Z', provenance='quoted_dialogue', project_id='alpha', session_id='synthetic')})
    (vault / '.knowledge_pipeline.json').write_text(json.dumps(state), encoding='utf-8')
    return vault, source_root


def grounded(question, rows, feedback=None):
    return dict(status='answered', answer='The retained decision selected SQLite for atomic writes.',
                record_ids=[rows[0]['record']['id']], inferences=[])


def test_question_context_and_answer_reuse_existing_records(qa_vault, monkeypatch):
    from selfos.app.knowledge_qa import question_context, answer_question
    vault, _ = qa_vault
    monkeypatch.setattr('selfos.sources.conversations.extract_conversations', lambda *a, **k: pytest.fail('QA scanned conversations'))
    context = question_context(vault)
    assert len(context['projects']) == 1 and context['projects'][0]['title'] == 'Synthetic importer'
    calls = []
    def answerer(question, rows, feedback=None):
        calls.append((question, rows, feedback))
        return grounded(question, rows, feedback)
    result = answer_question(vault, vault.parent, 'Why did we choose SQLite?', answerer=answerer)
    assert len(calls) == 1
    assert result['reply'] and result['answer_kind'] == 'model_interpretation'
    assert result['references'][0]['title'] == 'Synthetic importer'
    assert result['references'][0]['sources'][0]['id'] == 'm1'


def test_unsupported_question_never_calls_model(qa_vault):
    from selfos.app.knowledge_qa import answer_question
    vault, _ = qa_vault
    before = (vault / '.knowledge_pipeline.json').read_bytes()
    result = answer_question(vault, vault.parent, 'What is my blood type?',
        answerer=lambda *a, **k: pytest.fail('Unsupported personal question called model'))
    assert result['status'] == 'insufficient_evidence' and result['references'] == []
    assert 'evidence' in result['reply'].casefold()
    assert (vault / '.knowledge_pipeline.json').read_bytes() == before
    assert not (vault / '.knowledge_usage').exists()


def test_privacy_exclusions_remove_model_context_without_deleting_knowledge(qa_vault):
    from selfos.app.knowledge_qa import answer_question
    from selfos.sources.selection import save_sources
    vault, root = qa_vault
    before = (vault / '.knowledge_pipeline.json').read_bytes()
    save_sources(vault, {'roots': [str(root)], 'exclusions': [str(root)]})
    result = answer_question(vault, vault.parent, 'Why SQLite?',
        answerer=lambda *a, **k: pytest.fail('Excluded knowledge sent to model'))
    assert result['status'] == 'insufficient_evidence'
    assert (vault / '.knowledge_pipeline.json').read_bytes() == before


def test_durable_manual_correction_is_labeled_and_original_quote_preserved(qa_vault):
    from selfos.app.knowledge_qa import answer_question
    from selfos.app.library import list_knowledge
    from selfos.app.corrections import correct_knowledge
    vault, _ = qa_vault
    row = list_knowledge(vault, category='preferences')['items'][0]
    correct_knowledge(vault, dict(action='edit', ids=[row['id']],
        patch={'value': 'balanced', 'text': 'I prefer balanced explanations.'}))
    result = answer_question(vault, vault.parent, 'What are my preferences?', answerer=grounded)
    reference = result['references'][0]
    assert reference['user_corrected'] and reference['kind'] == 'user_correction'
    assert 'balanced' in reference['summary']
    assert 'concise' in reference['evidence']


def test_changed_knowledge_during_answer_is_not_returned_as_current(qa_vault):
    from selfos.app.knowledge_qa import answer_question, KnowledgeQAError
    vault, _ = qa_vault
    def mutate(question, rows, feedback=None):
        path = vault / '.knowledge_pipeline.json'
        state = json.loads(path.read_text(encoding='utf-8'))
        state['cards']['alpha']['intent'] = 'New corrected project scope'
        path.write_text(json.dumps(state), encoding='utf-8')
        return grounded(question, rows, feedback)
    with pytest.raises(KnowledgeQAError) as failure:
        answer_question(vault, vault.parent, 'Why SQLite?', answerer=mutate)
    assert failure.value.code == 'knowledge_changed'


def test_changed_privacy_during_answer_suppresses_response(qa_vault):
    from selfos.app.knowledge_qa import answer_question, KnowledgeQAError
    from selfos.sources.selection import save_sources
    vault, root = qa_vault
    def exclude(question, rows, feedback=None):
        save_sources(vault, {'roots': [str(root)], 'exclusions': [str(root)]})
        return grounded(question, rows, feedback)
    with pytest.raises(KnowledgeQAError) as failure:
        answer_question(vault, vault.parent, 'Why SQLite?', answerer=exclude)
    assert failure.value.code == 'knowledge_changed'


def test_invalid_model_output_gets_at_most_one_repair(qa_vault):
    from selfos.app.knowledge_qa import answer_question, KnowledgeQAError
    vault, _ = qa_vault
    calls = []
    def invalid(question, rows, feedback=None):
        calls.append(feedback)
        return dict(status='answered', answer='Invented fact', record_ids=['foreign'], inferences=[])
    with pytest.raises(KnowledgeQAError) as failure:
        answer_question(vault, vault.parent, 'Why SQLite?', answerer=invalid)
    assert failure.value.code == 'invalid_answer'
    assert len(calls) == 2 and calls[0] is None and calls[1]


def test_cancel_after_generation_prevents_repair_and_late_answer(qa_vault):
    from selfos.app.knowledge_qa import answer_question, KnowledgeQAError
    vault, _ = qa_vault
    stopped = [False]
    calls = []
    def cancel_during_answer(question, rows, feedback=None):
        calls.append(True)
        stopped[0] = True
        return {'invalid': 'output'}
    with pytest.raises(KnowledgeQAError) as failure:
        answer_question(vault, vault.parent, 'Why SQLite?', answerer=cancel_during_answer, cancel=lambda: stopped[0])
    assert failure.value.code == 'cancelled' and len(calls) == 1


def test_old_citation_does_not_silently_open_changed_record(qa_vault):
    from selfos.app.knowledge_qa import answer_question, validate_citation, KnowledgeQAError
    vault, _ = qa_vault
    result = answer_question(vault, vault.parent, 'Why SQLite?', answerer=grounded)
    citation = result['references'][0]
    assert validate_citation(vault, citation['id'], citation['revision'])['id'] == citation['id']
    path = vault / '.knowledge_pipeline.json'
    state = json.loads(path.read_text(encoding='utf-8'))
    state['cards']['alpha']['intent'] = 'Changed synthetic project'
    path.write_text(json.dumps(state), encoding='utf-8')
    with pytest.raises(KnowledgeQAError) as failure:
        validate_citation(vault, citation['id'], citation['revision'])
    assert failure.value.code == 'knowledge_changed'


def test_old_citation_rejects_changed_original_source_metadata(qa_vault):
    from selfos.app.knowledge_qa import answer_question, validate_citation, KnowledgeQAError
    vault, root = qa_vault
    citation = answer_question(vault, vault.parent, 'Why SQLite?', answerer=grounded)['references'][0]
    path = vault / '.knowledge_pipeline.json'
    state = json.loads(path.read_text(encoding='utf-8'))
    state['sources']['m1']['path'] = str(root / 'different.jsonl')
    path.write_text(json.dumps(state), encoding='utf-8')
    with pytest.raises(KnowledgeQAError, match='knowledge_changed'):
        validate_citation(vault, citation['id'], citation['revision'])


def test_corrupt_state_during_answer_is_explicitly_stale(qa_vault):
    from selfos.app.knowledge_qa import answer_question, KnowledgeQAError
    vault, _ = qa_vault
    def mutate(question, rows, feedback=None):
        (vault / '.knowledge_pipeline.json').write_text('{broken', encoding='utf-8')
        return grounded(question, rows, feedback)
    with pytest.raises(KnowledgeQAError, match='knowledge_changed'):
        answer_question(vault, vault.parent, 'Why SQLite?', answerer=mutate)


@pytest.mark.parametrize('state', [None, [], {'cards': []}, {'sources': []}])
def test_malformed_retained_state_fails_without_model_call(qa_vault, state):
    from selfos.app.knowledge_qa import answer_question, KnowledgeQAError
    vault, _ = qa_vault
    (vault / '.knowledge_pipeline.json').write_text(json.dumps(state), encoding='utf-8')
    with pytest.raises(KnowledgeQAError, match='knowledge_unavailable'):
        answer_question(vault, vault.parent, 'Why SQLite?', answerer=lambda *a, **k: pytest.fail('Malformed vault called model'))
