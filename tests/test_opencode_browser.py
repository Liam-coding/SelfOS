from selfos.web.rendering.resources import frontend_text
from selfos.web.i18n import catalogs


def test_source_setup_and_native_preview_have_explicit_controls_and_localized_copy():
    page = frontend_text('templates/onboarding.html')
    for identity in ('native-entries', 'native-path', 'native-add', 'native-dialog', 'native-start', 'native-status'):
        assert 'id="' + identity + '"' in page
    assert 'window.selfosHarness' in page
    script = frontend_text('scripts/opencode.js')
    assert 'native_preview=' in script
    assert 'data-i18n' in page
    for locale in ('en', 'zh-CN'):
        messages = catalogs()['locales'][locale]['messages']
        for key in ('title', 'help', 'preview', 'start', 'partial', 'unsupported_source_format', 'source_changed'):
            assert 'native.' + key in messages


def test_upload_picker_includes_only_explicitly_supported_export_json():
    assert 'accept=".txt,.md,.json"' in frontend_text('templates/uploads.html')


def test_source_save_preserves_typed_database_entries_and_project_exclusions():
    script = frontend_text('scripts/onboarding.js')
    assert 'selfosHarness.entries' in script
    assert 'project_exclusions' in script


def test_native_preview_wraps_long_project_paths_inside_dialog():
    assert '#native-excerpts{overflow-wrap:anywhere}' in frontend_text('styles/onboarding.css')
