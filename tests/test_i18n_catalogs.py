import json
import pytest


def test_default_alias_fallback_and_parameter_contract():
    from selfos.web.i18n import catalogs, normalize_locale, translate, validate_catalogs
    data = catalogs()
    assert normalize_locale(None) == 'en'
    assert normalize_locale('missing') == 'en'
    assert normalize_locale('zh') == 'zh-CN'
    assert translate('ui.common.greeting', params={'name': '<Fixture>'}) == 'Hello, <Fixture>'
    assert translate('ui.common.greeting', 'zh', {'name': 'Fixture'}) == '你好，Fixture'
    with pytest.raises(ValueError):
        translate('ui.common.greeting')
    assert validate_catalogs(data)['missing'].get('zh-CN', []) == []


def test_locale_discovery_and_missing_translation_fallback_need_no_feature_change(tmp_path):
    from selfos.web.i18n import load_catalogs, translate, normalize_locale, validate_catalogs
    for folder, metadata, messages in [
        ('en', {'name': 'English', 'tag': 'en', 'document_tag': 'en', 'aliases': []}, {'hello': 'Hello {name}', 'count': '{count} items'}),
        ('x-test', {'name': 'Test locale', 'tag': 'en-US', 'document_tag': 'x-test', 'aliases': ['xt']}, {'hello': 'Test hello {name}'})]:
        path = tmp_path / folder
        path.mkdir()
        (path / 'meta.json').write_text(json.dumps(metadata), encoding='utf-8')
        (path / 'ui.json').write_text(json.dumps(messages), encoding='utf-8')
    data = load_catalogs(tmp_path)
    assert normalize_locale('xt', data) == 'x-test'
    assert translate('ui.count', 'xt', {'count': 2}, data) == '2 items'
    assert validate_catalogs(data)['missing']['x-test'] == ['ui.count']
    data['locales']['x-test']['messages']['ui.hello'] = 'Wrong {other}'
    with pytest.raises(ValueError, match='parameter'):
        validate_catalogs(data)


def test_catalog_embedding_cannot_end_script_or_interpret_display_data():
    from selfos.web.i18n import catalogs, runtime
    data = catalogs()
    data['locales']['en']['messages']['ui.common.greeting'] = 'Hello {name} </script><script>unsafe()</script>'
    html = runtime(data)
    assert 'unsafe()</script>' not in html
    encoded = html.split('const catalogs=', 1)[1].split(',locales=', 1)[0]
    assert json.loads(encoded) == data


def test_duplicate_alias_and_nonstring_messages_are_rejected():
    from selfos.web.i18n import catalogs, validate_catalogs
    data = catalogs()
    data['locales']['zh-CN']['aliases'].append('en')
    with pytest.raises(ValueError, match='alias'):
        validate_catalogs(data)
    data = catalogs()
    data['locales']['en']['messages']['ui.invalid'] = 2
    with pytest.raises(ValueError, match='string'):
        validate_catalogs(data)


def test_auth_pages_use_shared_catalog_and_metadata_language_selectors():
    from selfos.web.rendering.auth import login_page, account_controls
    for page in (login_page(), account_controls()):
        assert 'window.selfosI18n=' in page
        assert 'const authLocales=' not in page
        assert 'data-auth-key' not in page
        assert 'data-i18n="auth.' in page
    assert 'populateLanguageSelect' in login_page()
    assert 'error.code=' in login_page()


@pytest.mark.parametrize('tag',['invalid_locale','en-1','en-','1en','en-a-abc-a-def','en-abc','zh-cmn'])
def test_invalid_intl_language_tags_are_rejected(tag):
    from selfos.web.i18n import catalogs,validate_catalogs
    data=catalogs();data['locales']['zh-CN']['tag']=tag
    with pytest.raises(ValueError,match='tag'):
        validate_catalogs(data)


@pytest.mark.parametrize('tag', ['en--US', 'en-1', 'en-', '1en', 'x-', 'en-a-abc-a-def'])
def test_invalid_document_language_tags_are_rejected(tag):
    from selfos.web.i18n import catalogs, validate_catalogs
    data = catalogs()
    data['locales']['zh-CN']['document_tag'] = tag
    with pytest.raises(ValueError, match='tag'):
        validate_catalogs(data)


def test_components_use_shared_runtime_without_duplicate_catalogs():
    from selfos.web.rendering.library import HTML
    from selfos.web.rendering.import_status import SCRIPT
    assert 'const searchLocales' not in HTML
    assert 'const importLocales' not in SCRIPT
