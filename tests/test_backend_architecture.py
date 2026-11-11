import selfos.providers.knowledge as _providers_knowledge
import selfos.storage.files as _storage_files
import selfos.sources.conversations as _sources_conversations
import selfos.sources.text as _sources_text
import selfos.web.server as _web_server
import ast
import importlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'src/selfos'
sys.path.insert(0, str(ROOT / 'src'))

def test_backend_has_separate_packages():
    for area in ('sources', 'knowledge', 'storage', 'providers', 'app', 'security', 'web'):
        assert (PACKAGE / area / '__init__.py').is_file(), area


def test_http_methods_have_separate_route_owners():

    assert _web_server.Handler._auth.__module__ == 'selfos.web.routes.auth'
    assert _web_server.Handler.do_GET.__module__ == 'selfos.web.routes.dashboard'
    assert _web_server.Handler.do_POST.__module__ == 'selfos.web.routes.actions'



def test_package_dependencies_are_one_way_and_acyclic():
    assert PACKAGE.exists(), 'backend package is missing'
    graph = {}
    legacy = {p.stem for p in ROOT.glob('*.py')}
    for path in PACKAGE.rglob('*.py'):
        name = '.'.join(path.relative_to(ROOT / 'src').with_suffix('').parts)
        edges = set()
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            imports = ([node.module] if isinstance(node, ast.ImportFrom) and node.module
                       else [a.name for a in node.names] if isinstance(node, ast.Import) else [])
            for target in imports:
                assert target.split('.')[0] not in legacy, (name, target)
                if target.startswith('selfos.'):
                    edges.add(target)
                    if name.startswith(('selfos.knowledge.', 'selfos.storage.', 'selfos.sources.')):
                        assert not target.startswith(('selfos.app.', 'selfos.web.', 'selfos.providers.')), (name, target)
        graph[name] = edges
    def visit(name, ancestors):
        assert name not in ancestors, ' -> '.join([*ancestors, name])
        for target in graph.get(name, ()):
            visit(target, [*ancestors, name])
    for name in graph:
        visit(name, [])
