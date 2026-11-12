import ast
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def rendering_hashes(tmp_path, monkeypatch):
    from selfos.web.rendering import auth, dashboard, knowledge, library, model, overall
    class FrozenDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 1, 1)
    monkeypatch.setattr(dashboard, 'date', FrozenDate)
    vault = tmp_path / 'vault'
    vault.mkdir(exist_ok=True)
    (vault / 'PROFILE.md').write_text('- Preferred name: Fixture User', encoding='utf-8')
    page = dashboard.generate_dashboard(vault, scores={key: 6 for key in dashboard._I18N})
    outputs = {'dashboard': page.read_text(encoding='utf-8'), 'login': auth.login_page(),
               'account': auth.ACCOUNT_CONTROLS, 'auth_style': auth.STYLE, 'auth_script': auth.SCRIPT,
               'import_controls': knowledge.CONTROLS, 'library_style': library.STYLE, 'library': library.HTML,
               'model': model.CONTROLS, 'visual_style': overall.STYLE, 'overview': overall.OVERVIEW}
    return {key: hashlib.sha256(value.encode('utf-8')).hexdigest() for key, value in outputs.items()}


def test_rendered_pages_and_components_preserve_current_main_bytes(tmp_path, monkeypatch):
    baseline = json.loads((ROOT / 'tests/fixtures/frontend_rendering_main_baseline.json').read_text(encoding='utf-8'))
    assert rendering_hashes(tmp_path, monkeypatch) == baseline['hashes']


def test_production_renderers_do_not_embed_large_ui_blocks():
    for path in (ROOT / 'src/selfos/web/rendering').glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 500:
                assert not any(tag in node.value for tag in ('<script>', '<style', '<div', '<main', '<form', '<dialog')), path.name


def test_package_loader_rejects_unknown_paths_and_preserves_value_boundaries(tmp_path, monkeypatch):
    from selfos.web.rendering.resources import frontend_text, render_ui
    monkeypatch.chdir(tmp_path)
    assert 'SelfOS' in frontend_text('templates/login-head.html')
    for path in ['../vault/PROFILE.md', '/etc/passwd', 'templates/missing.html', 'C:/private/.env']:
        with pytest.raises(ValueError):
            frontend_text(path)
    value = '@@SELFOS_RESOURCE:styles/visual-system.css@@ @@SELFOS_VALUE:value1@@'
    fields = dict(key=value, label_zh='', label_en='', display='', color='', status_zh='', status_en='',
                  sugg_zh='', sugg_en='', r='', arc='', circ='', hist_json='')
    rendered = render_ui('templates/dashboard-card.html', fields)
    assert value in rendered
    with pytest.raises(ValueError):
        render_ui('templates/dashboard-card.html', {})


def test_declared_include_cycles_are_rejected_without_reading_outside_package(tmp_path, monkeypatch):
    from selfos.web.rendering import resources
    web = tmp_path / 'web'
    web.mkdir()
    (web / 'a.html').write_text('@@SELFOS_RESOURCE:b.html@@', encoding='utf-8')
    (web / 'b.html').write_text('@@SELFOS_RESOURCE:a.html@@', encoding='utf-8')
    monkeypatch.setattr(resources, 'files', lambda package: tmp_path)
    monkeypatch.setattr(resources, '_names', lambda: frozenset(['a.html', 'b.html']))
    with pytest.raises(ValueError, match='Cyclic'):
        resources.frontend_text('a.html')


def test_declared_resource_manifest_covers_every_packaged_asset():
    from selfos.web.rendering.resources import frontend_text
    root = ROOT / 'src/selfos/resources/web'
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    actual = {path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file() and path.name != 'manifest.json'}
    assert set(manifest['resources']) == actual
    for name in manifest['resources']:
        assert '@@SELFOS_RESOURCE:' not in frontend_text(name)
