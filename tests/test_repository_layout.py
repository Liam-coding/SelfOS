from pathlib import Path
import subprocess
import sys
import runpy

ROOT = Path(__file__).resolve().parents[1]

def test_root_contains_only_supported_python_commands():
    assert not list(ROOT.glob('*.py'))

def test_generated_dashboard_is_not_tracked():
    result = subprocess.run(['git','ls-files','--','dashboard.html'],cwd=ROOT,capture_output=True,text=True,check=True)
    assert not result.stdout.strip()

def test_frozen_evaluation_has_a_compatible_launcher(tmp_path):
    result = subprocess.run([sys.executable,str(ROOT/'evals/run.py'),'--help'],cwd=tmp_path,
                            capture_output=True,text=True,encoding='utf-8')
    assert result.returncode == 0, result.stderr
    assert '--adapter' in result.stdout

def test_evaluation_launcher_requires_explicit_live_authorization(tmp_path):
    report = tmp_path / 'report.json'
    result = subprocess.run([sys.executable,str(ROOT/'evals/run.py'),'--adapter','pipeline','--output',str(report)],
                            cwd=tmp_path,capture_output=True,text=True,encoding='utf-8')
    assert result.returncode == 2
    assert 'Use --live' in result.stderr
    assert not report.exists()

def test_frozen_evaluator_uses_isolated_adapter_with_synthetic_output():
    import knowledge_pipeline
    from tests.test_project_knowledge_contract import summary
    assert Path(knowledge_pipeline.__file__).resolve().parent == ROOT / 'evals/adapters'
    evaluator = runpy.run_path(str(ROOT / 'evals/run_knowledge_eval.py'))
    case = {'id':'cleanup-smoke', 'category':'smoke', 'messages':[{'role':'user','text':'Build a reliable knowledge import.'}],
            'rubric':{'max_output_chars':10000,'empty_output':False,'required_concepts':[],'forbidden_claims':[]}}
    result = evaluator['evaluate_one'](case, summary, 'pipeline')
    assert result['passed'], result.get('error')
