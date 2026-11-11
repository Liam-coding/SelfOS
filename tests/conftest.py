import pytest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
# Only the byte-frozen acceptance contract needs the historical adapter name.
sys.path.insert(0, str(ROOT / 'evals/adapters'))

@pytest.fixture(autouse=True)
def isolate_auth_for_existing_behavior_tests(request,monkeypatch):
    # Existing HTTP tests exercise knowledge/local-origin behavior independently.
    # Authentication integration tests use the real gate without this substitution.
    if request.module.__name__.split('.')[-1].startswith('test_auth'):return
    import serve
    monkeypatch.setattr(serve.Handler,'_auth_guard',lambda self:True)
    monkeypatch.setattr(serve.Handler,'_session_alive',lambda self:True)
