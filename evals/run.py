"""Launch the frozen evaluator with its isolated historical import adapter."""
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'evals/adapters'))

if __name__ == '__main__':
    runpy.run_path(str(ROOT / 'evals/run_knowledge_eval.py'), run_name='__main__')
