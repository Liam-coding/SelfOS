import selfos.web.server as server
from tests.test_auth_http import http


def test_authenticated_cached_dashboard_refresh_is_read_only_and_runtime_is_early(http, monkeypatch):
    request, auth=http
    root=auth.vault.parent;root.mkdir(parents=True,exist_ok=True)
    dashboard=root/'dashboard.html'
    legacy='<!doctype html><html lang="zh"><head></head><body><pre>Literal private source</pre><script>// '+chr(0x2500)*2+' Theme '+chr(0x2500)*2+'\nlet isDark=false;const legacyMarker=true;</script></body></html>'
    dashboard.write_text(legacy,encoding='utf-8')
    monkeypatch.setattr(server,'DASHBOARD',dashboard)
    auth.reset('synthetic cached page password')
    cookie='selfos_session='+auth.login('synthetic cached page password')
    code,page,_=request('/',cookie=cookie)
    assert code==200
    assert page.count('id="selfos-i18n"')==1
    assert page.index('id="selfos-i18n"')<page.index('function openAppSettings')
    assert 'legacyMarker' not in page
    assert "selfosUI.register('theme'" in page
    assert 'Literal private source' in page
    assert dashboard.read_text(encoding='utf-8')==legacy


def test_legacy_cards_are_upgraded_without_losing_scores_history_or_sources():
    from selfos.web.rendering.refresh import refresh_dashboard
    original='<html><head></head><body><div class="card" data-key="career" data-score="6" data-label-en="Career" data-label-zh="legacy" data-status-en="OK" data-sugg-en="Define one near-term career goal and add it to GOALS.md"><canvas data-values="[1,2,6]"></canvas></div><p id="overall-date" data-en="Updated 2026-01-02" data-zh="legacy">2026-01-02</p><pre>Literal source</pre></body></html>'
    page=refresh_dashboard(original)
    assert 'data-label-key="ui.dimension.career"' in page
    assert 'data-status-key="ui.status.ok"' in page
    assert 'data-sugg-key="ui.suggestion.career.mid"' in page
    assert 'data-date="2026-01-02"' in page
    assert 'data-score="6"' in page and 'data-values="[1,2,6]"' in page
    assert '<pre>Literal source</pre>' in page


def test_refresh_current_generated_dashboard_keeps_layout_scores_and_single_owners(tmp_path):
    from selfos.web.rendering.dashboard import generate_dashboard
    from selfos.web.rendering.refresh import refresh_dashboard
    vault=tmp_path/'vault';vault.mkdir()
    original=generate_dashboard(vault,scores={'career':6}).read_text(encoding='utf-8')
    page=refresh_dashboard(original)
    again=refresh_dashboard(page)
    for candidate in (page,again):
        assert candidate.count('id="selfos-i18n"')==1
        assert candidate.count('function openAppSettings')==1
        assert candidate.count('let isDark')==1
        assert candidate.count('id="knowledge-library"')==1
        assert candidate.count('class="knowledge-overall"')==1
        assert candidate.index('class="header"')<candidate.index('class="knowledge-overview"')
        assert 'data-score="6"' in candidate


def test_legacy_decimal_score_gets_numeric_parameter_without_changing_text():
    from selfos.web.rendering.legacy_i18n import upgrade_legacy_markup
    from html.parser import HTMLParser
    import json
    source='<span class="overall-ring-num" title="Career">6.5</span>'
    page=upgrade_legacy_markup(source)
    class Score(HTMLParser):
        def handle_starttag(self,tag,attrs):
            values=dict(attrs)
            assert values['data-i18n']=='ui.common.value'
            assert json.loads(values['data-i18n-params'])['value']==6.5
            assert 'data-i18n-title' in values
    Score().feed(page)
    assert '>6.5</span>' in page
