"""Attribution is server-owned; model text never creates trusted sources."""
import pytest
from tests.test_knowledge_qa_retrieval import record


def selected():
    from selfos.knowledge.qa_retrieval import retrieve_records
    return retrieve_records([record('projects', 'Synthetic import', 'SQLite preserves atomic writes', status='active')], 'SQLite')


def test_valid_answer_uses_server_provenance_and_known_references():
    from selfos.knowledge.qa_output import validate_answer
    rows = selected()
    identity = rows[0]['record']['id']
    payload = dict(status='answered', answer='SQLite was selected for atomic local writes.',
                   record_ids=[identity], inferences=[])
    result = validate_answer(payload, rows)
    assert result['answer_kind'] == 'model_interpretation'
    assert result['references'][0]['id'] == identity
    assert result['references'][0]['sources'][0]['id'] == 's1'
    assert result['references'][0]['evidence'] == rows[0]['detail']['evidence']
    assert result['references'][0]['kind'] == 'inference'


@pytest.mark.parametrize('patch', [
    {'record_ids': ['foreign-record']}, {'record_ids': []}, {'record_ids': 's1'},
    {'status': 'verified_fact'}, {'answer': '<unsafe>'*1000}, {'sources': ['https://example.test']},
    {'inferences': [{'text': 'Unsupported inference', 'record_ids': ['foreign-record']}]},
])
def test_invalid_attribution_and_model_owned_provenance_are_rejected(patch):
    from selfos.knowledge.qa_output import validate_answer
    rows = selected()
    payload = dict(status='answered', answer='Supported summary', record_ids=[rows[0]['record']['id']], inferences=[])
    payload.update(patch)
    with pytest.raises(ValueError):
        validate_answer(payload, rows)


def test_insufficient_evidence_does_not_return_arbitrary_model_facts():
    from selfos.knowledge.qa_output import validate_answer
    result = validate_answer(dict(status='insufficient_evidence', answer='Invented personal fact', record_ids=[], inferences=[]), [])
    assert result['answer'] == '' and result['references'] == [] and result['inferences'] == []
