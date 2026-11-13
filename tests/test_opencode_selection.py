"""Explicit typed permissions and metadata-only OpenCode discovery."""
import json
from pathlib import Path

import pytest

from selfos.sources.selection import load_sources, save_sources, allowed_source, validate_selection
from selfos.app.privacy import permitted_source


def native_selection(path, **changes):
    return {'version': 2, 'entries': [{'kind': 'opencode_database', 'path': str(path)}],
            'exclusions': [], **changes}


def test_saved_v1_settings_keep_exact_bytes_and_do_not_gain_database_permission(tmp_path):
    from selfos.sources.selection import source_entries
    directory = tmp_path / 'existing'
    directory.mkdir()
    original = {'version': 1, 'roots': [str(directory)], 'exclusions': []}
    path = tmp_path / '.knowledge_sources.json'
    raw = json.dumps(original, indent=3).encode()
    path.write_bytes(raw)
    selected = load_sources(tmp_path)
    assert selected == original and path.read_bytes() == raw
    assert source_entries(selected) == [{'kind': 'directory', 'path': str(directory)}]
    assert not allowed_source(tmp_path / 'native.db', selected)


def test_database_entry_grants_only_the_exact_file_and_survives_save_load(tmp_path):
    database = tmp_path / 'native.db'
    database.write_bytes(b'Synthetic unread metadata fixture')
    selected = save_sources(tmp_path, native_selection(database))
    assert selected['roots'] == [] and load_sources(tmp_path) == selected
    assert allowed_source(database, selected)
    assert not allowed_source(tmp_path / 'sibling.db', selected)
    assert not allowed_source(tmp_path, selected)


def test_mixed_directory_database_selection_preserves_legacy_directory_view(tmp_path):
    directory = tmp_path / 'sessions'
    directory.mkdir()
    database = tmp_path / 'native.db'
    database.touch()
    selected = save_sources(tmp_path, {'version': 2, 'entries': [
        {'kind': 'directory', 'path': str(directory)}, {'kind': 'opencode_database', 'path': str(database)}],
        'exclusions': [str(directory / 'excluded')]})
    assert selected['roots'] == [str(directory)]
    assert allowed_source(directory / 'conversation.jsonl', selected)
    assert not allowed_source(directory / 'excluded/conversation.jsonl', selected)


@pytest.mark.parametrize('kind', ['sqlite', 'unknown', '', None])
def test_unknown_adapters_cannot_grant_source_permission(tmp_path, kind):
    with pytest.raises(ValueError):
        validate_selection({'version': 2, 'entries': [{'kind': kind, 'path': str(tmp_path / 'native.db')}]})


def test_compatibility_roots_cannot_hide_additional_permission(tmp_path):
    value = native_selection(tmp_path / 'native.db', roots=[str(tmp_path / 'unlisted')])
    with pytest.raises(ValueError):
        validate_selection(value)


def test_saving_unavailable_database_does_not_publish_selection(tmp_path):
    with pytest.raises(ValueError):
        save_sources(tmp_path, native_selection(tmp_path / 'missing.db'))
    assert not (tmp_path / '.knowledge_sources.json').exists()


def test_storage_and_project_exclusions_are_separate(tmp_path):
    from selfos.sources.selection import project_allowed
    database = tmp_path / 'data/native.db'
    excluded = tmp_path / 'sensitive-project'
    selected = validate_selection(native_selection(database, project_exclusions=[str(excluded)]))
    assert allowed_source(database, selected)
    assert not project_allowed(str(excluded / 'subdirectory'), selected)
    assert project_allowed(str(tmp_path / 'other-project'), selected)
    source = {'source': 'opencode', 'path': str(database), 'cwd': str(excluded),
              'project_id': 'opencode-project:native_opaque_id'}
    assert not permitted_source(source, selected, tmp_path)
    source['cwd'] = str(tmp_path / 'other-project')
    assert permitted_source(source, selected, tmp_path)


def test_unknown_project_scope_is_conservative_only_for_native_project_exclusions(tmp_path):
    from selfos.sources.selection import project_allowed
    selected = validate_selection(native_selection(tmp_path / 'native.db', project_exclusions=[str(tmp_path / 'private')]))
    assert not project_allowed('', selected)
    assert project_allowed('', validate_selection(native_selection(tmp_path / 'native.db')))
    uploaded = {'source': 'uploaded_file', 'path': '.knowledge_uploads/originals/synthetic.txt',
                'project_id': 'uploaded-document:opaque'}
    assert permitted_source(uploaded, selected, tmp_path)


def test_native_opaque_project_id_is_never_resolved_as_a_filesystem_path(tmp_path, monkeypatch):
    database = tmp_path / 'native.db'
    selected = validate_selection(native_selection(database))
    original = Path.resolve
    def resolve(path, *args, **kwargs):
        if str(path).startswith('opencode-project:'):
            pytest.fail('Opaque IDs cannot become filesystem paths')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'resolve', resolve)
    assert permitted_source({'source': 'opencode', 'path': str(database), 'project_id': 'opencode-project:opaque'}, selected, tmp_path)


@pytest.mark.parametrize('override', [None, 'custom.db', 'nested/channel.db', 'absolute'])
def test_discovery_respects_xdg_and_explicit_database_filename(tmp_path, override):
    from selfos.sources.opencode_discovery import discover_opencode
    home, data = tmp_path / 'home', tmp_path / 'data'
    environment = {'XDG_DATA_HOME': str(data)}
    expected = data / 'opencode/opencode.db'
    if override == 'absolute':
        expected = tmp_path / 'explicit.db'
        environment['OPENCODE_DB'] = str(expected)
    elif override is not None:
        expected = data / 'opencode' / override
        environment['OPENCODE_DB'] = override
    expected.parent.mkdir(parents=True, exist_ok=True)
    expected.touch()
    candidates = discover_opencode(environ=environment, home=home)
    assert len(candidates) == 1
    assert candidates[0]['path'] == str(expected.resolve())
    assert candidates[0]['available'] and candidates[0]['kind'] == 'opencode_database'


def test_relative_xdg_and_config_test_home_do_not_redirect_data(tmp_path):
    from selfos.sources.opencode_discovery import discover_opencode
    home = tmp_path / 'home'
    candidates = discover_opencode(home=home, environ={'XDG_DATA_HOME': 'relative',
        'OPENCODE_CONFIG_DIR': str(tmp_path / 'config'), 'OPENCODE_TEST_HOME': str(tmp_path / 'test')})
    assert candidates[0]['path'] == str((home / '.local/share/opencode/opencode.db').resolve())
    assert not candidates[0]['available']


@pytest.mark.parametrize('override', [':memory:', '../../outside.db'])
def test_unreadable_memory_or_escaping_relative_override_is_explicit(tmp_path, override):
    from selfos.sources.opencode_discovery import discover_opencode
    candidate = discover_opencode(home=tmp_path, environ={'OPENCODE_DB': override})[0]
    assert candidate['path'] is None and not candidate['available']
    assert candidate['status'] in ('memory_unavailable', 'invalid_override')


def test_discovery_does_not_read_or_initialize_transcript_bodies(tmp_path, monkeypatch):
    from selfos.sources.opencode_discovery import discover_opencode
    path = tmp_path / '.local/share/opencode/opencode.db'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'Synthetic unread storage')
    monkeypatch.setattr(Path, 'open', lambda *args, **kwargs: pytest.fail('Discovery is metadata-only'))
    assert discover_opencode(home=tmp_path, environ={})[0]['available']
