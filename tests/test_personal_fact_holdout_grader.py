import runpy
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
evaluate=runpy.run_path(str(ROOT/'evals/run_personal_fact_holdout.py'))['evaluate']


def case(identity,expected,role='user'):
    return {'id':identity,'text':'I work as a designer.','key':'employment.role',
        'value':'designer','role':role,'expected_current':expected}


def test_grader_compares_labels_to_actual_predictions_without_treating_quotes_as_truth():
    # Deliberately contradictory labels check grading, not factual policy quality.
    report=evaluate([case('true-positive',True),case('false-positive',False),
                     case('false-negative',True,'assistant'),case('true-negative',False,'assistant')])
    assert report['true_positive']==1 and report['false_positive']==1 and report['false_negative']==1
    assert report['precision']==0.5 and report['recall']==0.5
    assert report['structural_source_traceability']==1
    assert report['scope']=='record_validation_and_retention_only' and report['model_calls']==0


def test_empty_predictions_do_not_report_perfect_precision_or_traceability():
    report=evaluate([case('assistant',False,'assistant')])
    assert report['precision'] is None and report['recall'] is None
    assert report['structural_source_traceability'] is None


def test_invalid_evidence_is_recorded_as_rejected_instead_of_a_retained_prediction():
    value=case('untraceable',False);value['evidence']='Invented quotation'
    report=evaluate([value])
    assert report['rows'][0]['rejected_invalid']
    assert not report['rows'][0]['retained_current']
