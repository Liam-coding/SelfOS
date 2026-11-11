"""Tests for the evaluation ruler, independent of generated model answers."""
import importlib.util
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[1] / 'evals' / 'run_knowledge_eval.py'
spec = importlib.util.spec_from_file_location('knowledge_eval_grader', path)
grader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grader)


def case(**changes):
    rubric = {'required_concepts': [['cache', '缓存'], ['retry', '重试']],
              'forbidden_claims': ['all tests passed'], 'empty_output': False, 'max_output_chars': 100}
    rubric.update(changes)
    return {'id': 'ruler', 'category': 'ruler checks', 'rubric': rubric}


@pytest.mark.parametrize('text', ['Use cache and retry.', '使用缓存和重试。', 'CACHE with RETRY'])
def test_equivalent_declared_concept_alternatives_pass(text):
    assert grader.grade_case(case(), [text])['passed'] is True


@pytest.mark.parametrize('text', ['Use cache.', 'Use retry.', 'No durable content.'])
def test_missing_required_concept_fails(text):
    assert grader.grade_case(case(), [text])['passed'] is False


def test_forbidden_claim_fails_even_when_required_concepts_present():
    assert grader.grade_case(case(), ['cache retry all tests passed'])['passed'] is False


def test_unknown_source_fails_even_when_text_looks_correct():
    assert grader.grade_case(case(), ['cache retry'], source_valid=False)['passed'] is False


def test_code_dump_fails_even_when_text_contains_required_words():
    assert grader.grade_case(case(), ['cache retry ' + chr(96)*3 + 'code'])['passed'] is False


def test_excessive_output_fails():
    assert grader.grade_case(case(), ['cache retry ' + 'x'*100])['passed'] is False


def test_pure_noise_case_requires_no_saved_output():
    noise = case(required_concepts=[], forbidden_claims=[], empty_output=True)
    assert grader.grade_case(noise, [])['passed'] is True
    assert grader.grade_case(noise, ['Running now.'])['passed'] is False


def test_source_ids_and_status_flags_cannot_satisfy_text_concepts():
    output = {'source_ids': ['cache retry'], 'verified': True, 'project_id': 'cache/retry'}
    assert grader.grade_case(case(), output)['passed'] is False


def test_project_and_lesson_text_both_contribute_to_concept_checks():
    output = {'project': {'intent': 'Use cache'}, 'lessons': [{'text': 'Use retry', 'source_ids': ['m1']}]}
    assert grader.grade_case(case(), output)['passed'] is True
