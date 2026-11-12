"""Publication status uses actual synthetic imports, never live conversations."""
import json

import pytest

from selfos.app.knowledge import get_status, run_knowledge
from tests.test_knowledge_service import source, summarize, refine


def test_stopped_saved_session_is_distinct_from_published_and_resumes(tmp_path):
    roots, original = source(tmp_path)
    raw = original.read_bytes()
    vault = tmp_path / 'vault'
    stopped = [False]

    def progress(line):
        if line.startswith('Saved session '):
            stopped[0] = True

    result = run_knowledge(vault, roots=[roots], summarize=summarize,
                           refine=refine, cancel=lambda: stopped[0], progress=progress)
    assert result['status'] == 'stopped' and not result['installed']
    status = get_status(vault)
    assert status['counts']['preferences'] == 0
    assert status['saved_checkpoints'] == 1
    operation = status['publication']['operations'][0]
    assert operation['status'] == 'stopped'
    assert operation['phase'] == 'extracting'
    assert operation['staged_counts']['preferences'] == 1
    assert operation['compatible'] is True
    assert operation['published'] is False

    result = run_knowledge(vault, roots=[roots],
        summarize=lambda _: pytest.fail('saved extraction must be reused'), refine=refine)
    assert result['installed']
    status = get_status(vault)
    assert status['counts']['preferences'] == 1
    assert status['publication']['published_operation'] == result['operation_id']
    assert all(not op['resume_eligible'] for op in status['publication']['operations'])
    assert all(op['staged_snapshot_published'] for op in status['publication']['operations'])
    assert original.read_bytes() == raw


def test_failed_refinement_reports_phase_without_private_error_text(tmp_path):
    roots, _ = source(tmp_path)
    vault = tmp_path / 'vault'

    def fail(_):
        raise ValueError('PRIVATE SOURCE TEXT must not be in status')

    result = run_knowledge(vault, roots=[roots], summarize=summarize, refine=fail)
    assert result['status'] == 'failed' and not result['installed']
    status = get_status(vault)
    operation = status['publication']['operations'][0]
    assert operation['status'] == 'failed'
    assert operation['phase'] == 'refining'
    assert operation['staged_counts']['preferences'] == 1
    assert status['counts']['preferences'] == 0
    assert 'PRIVATE SOURCE TEXT' not in json.dumps(status)


def test_legacy_staging_is_unknown_not_guessed_failed(tmp_path):
    from selfos.storage.settings import load_settings
    vault = tmp_path / 'vault'
    scratch = vault / '.knowledge_rebuild' / ('a' * 24)
    scratch.mkdir(parents=True)
    state = {'policy': load_settings(vault), 'cache': {}, 'summaries': {},
             'preferences': [{'key': 'style', 'value': 'concise'}]}
    (scratch / '.knowledge_pipeline.json').write_text(json.dumps(state), encoding='utf-8')
    before = {str(p.relative_to(vault)): p.read_bytes() for p in vault.rglob('*') if p.is_file()}
    status = get_status(vault)
    operation = status['publication']['operations'][0]
    assert operation['status'] == 'unknown'
    assert operation['phase'] == 'unknown'
    assert operation['staged_counts']['preferences'] == 1
    after = {str(p.relative_to(vault)): p.read_bytes() for p in vault.rglob('*') if p.is_file()}
    assert before == after


def journal_fixture(vault, *, status='running', phase='refining', owner_pid=12345):
    from selfos.app.import_status import RunJournal
    from selfos.knowledge.settings import policy_hash
    from selfos.storage.settings import load_settings
    journal = RunJournal(vault, '20261112T010000-' + 'b' * 12, 'incremental',
                         'absent', policy_hash(load_settings(vault)))
    journal.update(status=status, phase=phase, owner_pid=owner_pid)
    return journal


def test_dead_owner_is_interrupted_but_live_owner_is_not(tmp_path, monkeypatch):
    import selfos.app.import_status as module
    vault = tmp_path / 'vault'
    journal_fixture(vault)
    monkeypatch.setattr(module, '_pid_alive', lambda _: False)
    assert get_status(vault)['publication']['operations'][0]['status'] == 'interrupted'
    monkeypatch.setattr(module, '_pid_alive', lambda _: True)
    assert get_status(vault)['publication']['operations'][0]['status'] == 'running'


@pytest.mark.parametrize('bad', [[], {'cache': []}, {'preferences': None},
                                 {'cards': {'bad': None}}, {'records_history': 'not records'},
                                 {'project_observations': 'not records'},
                                 {'cards': {'bad': {'state_records': 'not records'}}}])
def test_malformed_staging_has_bounded_diagnostics(tmp_path, bad):
    vault = tmp_path / 'vault'
    checkpoint = 'c' * 24
    journal = journal_fixture(vault, status='failed')
    journal.update(checkpoint=checkpoint)
    path = vault / '.knowledge_rebuild' / checkpoint / '.knowledge_pipeline.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(bad), encoding='utf-8')
    status = get_status(vault)
    assert status['publication']['diagnostics'] > 0
    assert status['publication']['operations'][0]['staged_counts'] is None


def test_settings_change_makes_checkpoint_incompatible(tmp_path):
    from selfos.storage.settings import save_settings
    vault = tmp_path / 'vault'
    journal_fixture(vault, status='stopped')
    save_settings(vault, {'domains': ['personal'], 'detail': 'concise'})
    operation = get_status(vault)['publication']['operations'][0]
    assert operation['compatible'] is False
    assert operation['policy_compatible'] is False
    assert operation['resume_eligible'] is False


def test_journal_io_failure_cannot_invalidate_publication(tmp_path, monkeypatch):
    import selfos.app.import_status as module
    roots, _ = source(tmp_path)
    vault = tmp_path / 'vault'
    monkeypatch.setattr(module, '_atomic_write', lambda *_: (_ for _ in ()).throw(OSError('disk')))
    result = run_knowledge(vault, roots=[roots], summarize=summarize, refine=refine)
    assert result['installed'] and result['status'] == 'completed'
    assert get_status(vault)['counts']['preferences'] == 1


def test_stale_running_journal_cannot_hide_successful_publication(tmp_path, monkeypatch):
    import selfos.app.import_status as module
    roots, _ = source(tmp_path)
    vault = tmp_path / 'vault'
    result = run_knowledge(vault, roots=[roots], summarize=summarize, refine=refine)
    path = vault / '.knowledge_jobs' / 'operations' / (result['operation_id'] + '.json')
    journal = json.loads(path.read_text())
    journal.update(status='running', phase='publishing')
    path.write_text(json.dumps(journal), encoding='utf-8')
    monkeypatch.setattr(module, '_pid_alive', lambda _: False)
    operation = get_status(vault)['publication']['operations'][0]
    assert operation['status'] == 'completed' and operation['published']
    assert not operation['resume_eligible']


def test_changed_canonical_base_is_not_resumable_as_same_operation(tmp_path):
    vault = tmp_path / 'vault'
    journal_fixture(vault, status='stopped')
    (vault / '.knowledge_pipeline.json').write_text('{}', encoding='utf-8')
    operation = get_status(vault)['publication']['operations'][0]
    assert operation['policy_compatible'] is True
    assert operation['compatible'] is False


def test_external_staging_symlink_is_not_read(tmp_path):
    vault = tmp_path / 'vault'
    checkpoint = 'd' * 24
    journal_fixture(vault, status='failed').update(checkpoint=checkpoint)
    external = tmp_path / 'external'
    external.mkdir()
    (external / '.knowledge_pipeline.json').write_text('{"preferences": []}', encoding='utf-8')
    staging = vault / '.knowledge_rebuild'
    staging.mkdir()
    try:
        (staging / checkpoint).symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip('Directory symlinks unavailable in this environment')
    status = get_status(vault)
    assert status['publication']['diagnostics'] > 0
    assert status['publication']['operations'][0]['staged_counts'] is None


def test_journal_cannot_claim_compatibility_with_different_staging_policy(tmp_path):
    from selfos.storage.settings import load_settings
    vault = tmp_path / 'vault'
    journal = journal_fixture(vault, status='stopped')
    checkpoint = 'e' * 24
    journal.update(checkpoint=checkpoint)
    path = vault / '.knowledge_rebuild' / checkpoint / '.knowledge_pipeline.json'
    path.parent.mkdir(parents=True)
    policy = load_settings(vault)
    policy['detail'] = 'concise'
    path.write_text(json.dumps({'policy': policy, 'cache': {}, 'summaries': {}}), encoding='utf-8')
    operation = get_status(vault)['publication']['operations'][0]
    assert not operation['compatible'] and not operation['resume_eligible']


def test_invalid_journal_date_does_not_expose_private_text(tmp_path):
    vault = tmp_path / 'vault'
    journal_fixture(vault, status='failed').update(updated_at='PRIVATE DATE TEXT')
    # update() sets a real timestamp; corrupt the file to simulate external edits.
    path = next((vault / '.knowledge_jobs' / 'operations').glob('*.json'))
    data = json.loads(path.read_text())
    data['updated_at'] = 'PRIVATE DATE TEXT'
    path.write_text(json.dumps(data), encoding='utf-8')
    status = get_status(vault)
    assert 'PRIVATE DATE TEXT' not in json.dumps(status)


def test_keyboard_interrupt_preserves_saved_work_as_interrupted(tmp_path):
    roots, _ = source(tmp_path)
    vault = tmp_path / 'vault'
    def interrupt(_):
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        run_knowledge(vault, roots=[roots], summarize=summarize, refine=interrupt)
    operation = get_status(vault)['publication']['operations'][0]
    assert operation['status'] == 'interrupted'
    assert operation['phase'] == 'refining'
    assert operation['resume_eligible'] is True


def test_unknown_legacy_checkpoints_offer_explicit_source_recheck(tmp_path):
    from selfos.storage.settings import load_settings
    vault = tmp_path / 'vault'
    path = vault / '.knowledge_rebuild' / ('f' * 24) / '.knowledge_pipeline.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'policy': load_settings(vault),
        'cache': {'session': 'fingerprint'}, 'summaries': {'session': {}}}), encoding='utf-8')
    operation = get_status(vault)['publication']['operations'][0]
    assert operation['status'] == 'unknown' and operation['compatible'] is None
    assert operation['resume_eligible'] is False
    assert operation['source_recheck_available'] is True
