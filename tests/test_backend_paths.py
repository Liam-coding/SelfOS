import selfos.web.server as _web_server
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

def test_explicit_root_is_independent_of_cwd(tmp_path, monkeypatch):
    assert importlib.util.find_spec('selfos.paths'), 'central paths are missing'
    from selfos.paths import AppPaths
    project = tmp_path / 'project'
    monkeypatch.chdir(tmp_path)
    paths = AppPaths.from_root(project)
    assert paths.root == project.resolve()
    assert paths.vault == project / 'vault'
    assert paths.model_config == project / '.selfos-model.json'
    assert paths.auth_marker == project / '.selfos-auth-required'

def test_auth_locales_are_package_resources():
    from selfos.web.rendering.auth import resources
    value = resources()
    assert 'en' in value and 'zh' in value
    assert value['en']['login'] == 'Log in'


def test_installed_module_commands_accept_root_from_foreign_cwd(tmp_path):
    for command in ('serve', 'knowledge', 'harvest', 'auth'):
        env = {**os.environ, 'PYTHONPATH': str(ROOT / 'src')}
        run = subprocess.run([sys.executable, '-m', 'selfos', command, '--root', str(tmp_path / 'data'), '--help'],
                             cwd=tmp_path, env=env, capture_output=True, text=True, encoding='utf-8')
        assert run.returncode == 0, run.stderr
        assert '--root' in run.stdout
    assert not (tmp_path / 'data').exists()

def test_http_child_command_works_without_checkout_scripts(tmp_path):
    from selfos.app import jobs
    assert hasattr(jobs, 'command'), 'package task launcher is missing'
    cmd = jobs.command('knowledge', tmp_path, '--help')
    run = subprocess.run(cmd, cwd=tmp_path, env=jobs.child_environment(), capture_output=True,
                         text=True, encoding='utf-8')
    assert run.returncode == 0, run.stderr
    assert '--vault' in run.stdout
    assert not (tmp_path / 'vault').exists()

@pytest.mark.parametrize('explicit_root', [True, False])
def test_knowledge_config_root_is_separate_from_vault(tmp_path, monkeypatch, explicit_root):
    import json
    from selfos.app import knowledge_cli, knowledge
    from selfos.providers import client
    app = tmp_path / 'app'
    vault = tmp_path / 'data/vault'
    app.mkdir()
    vault.parent.mkdir()
    for root in (app, vault.parent):
        (root / '.selfos-model.json').write_text(json.dumps({'provider':'openai', 'api_key':'fixture',
            'model':'fixture-model', 'base_url':'http://localhost:9999/v1', 'proxy_mode':'direct'}))
    opened = []
    def opener(root):
        opened.append(Path(root).resolve())
        return lambda *args, **kwargs: pytest.fail('This routing test must not call a model')
    monkeypatch.setattr(client, 'request_opener', opener)
    monkeypatch.setattr(knowledge, 'run_knowledge', lambda selected, **kwargs:
        {'installed':False, 'status':'completed', 'model_calls':0, 'operation_id':'fixture'})
    args = ['knowledge', '--vault', str(vault)]
    if explicit_root:
        args += ['--root', str(app)]
    monkeypatch.setattr(sys, 'argv', args)
    knowledge_cli.main()
    assert opened == [app if explicit_root else vault.parent] * 2
    assert not vault.exists()

def test_server_starts_with_a_new_data_directory(tmp_path, monkeypatch):
    import webbrowser
    from selfos.web import server
    root = tmp_path / 'new-installation'
    for name in ('ROOT', 'VAULT', 'DASHBOARD'):
        monkeypatch.setattr(server, name, getattr(server, name))
    monkeypatch.setattr(sys, 'argv', ['serve', '--root', str(root), '--port', '0'])
    monkeypatch.setattr(webbrowser, 'open', lambda _: None)
    def stop(server_instance):
        raise KeyboardInterrupt
    monkeypatch.setattr(server.HTTPServer, 'serve_forever', stop)
    server.main()
    assert (root / 'dashboard.html').is_file()
    assert not (root / '.selfos-model.json').exists()
    assert not (root / 'vault/.knowledge_pipeline.json').exists()
