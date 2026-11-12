import json
import runpy
import subprocess
import sys
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
API=runpy.run_path(str(ROOT/'evals/run_source_session_holdout.py'))


def test_missing_outputs_are_not_reported_as_a_passing_model_evaluation():
    data=json.loads((ROOT/'evals/source_session_holdout.json').read_text(encoding='utf-8'))
    result=API['score'](data,{})
    assert result['true_positive']==0
    assert result['false_negative']>0
    assert all(row.get('missing_prediction') for row in result['cases'])
    assert result['precision'] is None


def test_scoring_separates_wrong_scope_from_valid_provenance():
    case={'id':'scope-case','text':'For work emails I prefer concise explanations.',
          'expected':[{'category':'preferences','key':'communication.detail','values':['concise'],
                       'scope_type':'activity','scopes':['work-email']}]}
    raw={'key':'communication.detail','value':'concise','text':'Concise explanations',
         'kind':'user_fact','domain':'personal','temporal':'current',
         'scope':{'type':'global','id':''},'source_ids':['scope-case-user'],'evidence':case['text']}
    result=API['score']({'cases':[case]},{'scope-case':{'project':None,'lessons':[],'preferences':[raw]}})
    assert result['structurally_traceable_retained']==1
    assert result['false_positive']==1 and result['false_negative']==1
    assert result['precision']==0


def test_live_evaluation_requires_explicit_model_call_flag(tmp_path):
    env=dict(os.environ)
    env['ANTHROPIC_API_KEY']='';env['OPENAI_API_KEY']=''
    result=subprocess.run([sys.executable,str(ROOT/'evals/run_source_session_holdout.py'),
        '--model-root',str(tmp_path),'--output',str(tmp_path/'report.json')],
        capture_output=True,text=True,env=env,timeout=15)
    assert result.returncode==2
    assert '--allow-model-calls' in result.stderr
    assert not (tmp_path/'report.json').exists()
