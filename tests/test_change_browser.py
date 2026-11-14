from selfos.web.rendering.refresh import refresh_dashboard
from selfos.web.i18n import translate,catalogs

def test_cached_dashboard_gets_one_localized_changes_dialog_after_repeated_refresh():
    from selfos.web.rendering.resources import frontend_text
    page=refresh_dashboard(frontend_text('templates/dashboard-page.html'))
    page=refresh_dashboard(page)
    assert page.count('id="knowledge-changes"')==1
    assert page.count('id="knowledge-changes-entry"')==1
    assert 'data-i18n="changes.title"' in page
    assert 'id="changes-before-after"' in page

def test_changes_catalogs_explain_historical_values_and_omitted_history():
    data=catalogs()
    assert translate('changes.title',data=data)=='Knowledge changes'
    assert translate('changes.title','zh-CN',data=data)=='知识变化'
    assert 'export' in translate('changes.not_included',data=data)
    assert translate('changes.historical',data=data)!='changes.historical'
    assert '?' not in translate('changes.backup_restored','zh-CN',data=data)
