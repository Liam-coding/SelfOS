"""Guide state operations never implicitly start model or knowledge tasks."""
import json
import pytest


def test_read_skip_resume_do_not_touch_settings_or_knowledge(tmp_path, monkeypatch):
    from selfos.app.onboarding import onboarding_status, onboarding_action
    import selfos.sources.selection as sources
    root = tmp_path / 'source'
    root.mkdir()
    monkeypatch.setattr(sources, 'local_roots', lambda: [root])
    vault = tmp_path / 'vault'
    before = onboarding_status(vault, tmp_path)
    assert before['progress']['step'] == 0
    assert not vault.exists()
    onboarding_action(vault, tmp_path, {'action': 'save_step', 'step': 2})
    onboarding_action(vault, tmp_path, {'action': 'skip'})
    state = onboarding_action(vault, tmp_path, {'action': 'resume'})
    assert state['progress']['step'] == 2
    assert state['progress']['status'] == 'active'
    assert not (vault / '.knowledge_pipeline.json').exists()
    assert not (tmp_path / '.model_settings.json').exists()


def test_empty_preview_cannot_start_and_corrupt_progress_is_not_reset(tmp_path, monkeypatch):
    from selfos.app.onboarding import onboarding_action, onboarding_status
    import selfos.sources.selection as sources
    root = tmp_path / 'source'
    root.mkdir()
    monkeypatch.setattr(sources, 'local_roots', lambda: [root])
    vault = tmp_path / 'vault'
    result = onboarding_action(vault, tmp_path, {'action': 'preview'})
    with pytest.raises(ValueError):
        onboarding_action(vault, tmp_path, {'action': 'start', 'preview_id': result['preview']['id']})
    path = vault / '.knowledge_onboarding.json'
    path.write_text('{"version": 999}', encoding='utf-8')
    with pytest.raises(ValueError):
        onboarding_status(vault, tmp_path)
    assert json.loads(path.read_text()) == {'version': 999}


@pytest.mark.parametrize('body', [{'action': 'save_step', 'step': True},
                                    {'action': 'save_step', 'step': 9},
                                    {'action': 'resume', 'api_key': 'never-save-this'},
                                    {'action': 'start', 'preview_id': '../invalid'}])
def test_invalid_guide_actions_fail_before_writing(tmp_path, body):
    from selfos.app.onboarding import onboarding_action
    with pytest.raises(ValueError):
        onboarding_action(tmp_path / 'vault', tmp_path, body)
    assert not (tmp_path / 'vault').exists()
