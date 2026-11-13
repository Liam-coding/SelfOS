import json
from selfos.web.rendering.refresh import refresh_dashboard
from selfos.web.i18n import catalogs


def test_cached_dashboard_has_single_quality_report():
    page = refresh_dashboard('<html><head></head><body></body></html>')
    page = refresh_dashboard(page)
    assert page.count('id="knowledge-quality"') == 1
    assert '/__knowledge_quality__' in page
    assert 'encodeURIComponent(identity)' in page
    assert 'quality.incomplete' in page


def test_report_catalog_parity():
    data = catalogs()['locales']
    en = {key for key in data['en']['messages'] if key.startswith('quality.')}
    zh = {key for key in data['zh-CN']['messages'] if key.startswith('quality.')}
    assert 'quality.reviewed_zero' in en
    assert en == zh
