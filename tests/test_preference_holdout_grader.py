import runpy
from pathlib import Path

evaluate=runpy.run_path(str(Path(__file__).resolve().parents[1]/'evals/run_preference_holdout.py'))['evaluate']


def candidate(identity,expected,role='user'):
    return {'id':identity,'text':'I prefer concise explanations.','value':'concise','expected':expected,'role':role}


def test_candidate_labels_grade_predictions_and_keep_traceability_separate():
    # Intentionally contradictory labels test the evaluator's confusion matrix.
    report=evaluate({'candidates':[candidate('tp',True),candidate('fp',False),candidate('fn',True,'assistant')],
        'sequences':[]})
    assert (report['true_positive'],report['false_positive'],report['false_negative'])==(1,1,1)
    assert report['precision']==report['recall']==0.5
    assert report['structural_source_traceability']==1 and report['model_calls']==0


def test_sequence_grader_requires_expected_scope_value_history_and_support():
    records=[{'text':'I prefer concise explanations.','value':'concise','at':'2026-01-01T10:00:00Z'},
        {'text':'From now on, I prefer detailed explanations.','value':'detailed','at':'2026-02-01T10:00:00Z'}]
    good={'id':'good','records':records,'expected_current':[['global','detailed']],
        'expected_history':['concise'],'expected_support':1}
    bad={**good,'id':'wrong-history','expected_history':['invented']}
    report=evaluate({'candidates':[],'sequences':[good,bad]})
    assert report['sequence_passes']==1
    assert report['sequences'][0]['passed'] and not report['sequences'][1]['passed']


def test_no_retained_records_do_not_claim_perfect_precision_or_traceability():
    report=evaluate({'candidates':[candidate('assistant',False,'assistant')],'sequences':[]})
    assert report['precision'] is None and report['structural_source_traceability'] is None
