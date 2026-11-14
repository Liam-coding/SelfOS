def test_cached_refresh_keeps_one_owner_for_design_and_privacy():
    from selfos.web.rendering import model, knowledge, overall
    from selfos.web.rendering.refresh import refresh_dashboard
    from selfos.web.rendering.resources import frontend_text
    page='<html><head><style id="selfos-design-tokens">'+frontend_text('styles/tokens.css')+'</style>'+overall.STYLE+'</head><body>'+model.CONTROLS+knowledge.CONTROLS+'<script>window.keepCustomStyleTask=true;</script></body></html>'
    for _ in range(3):
        page=refresh_dashboard(page)
        assert page.count('id="selfos-design-tokens"')==1
        assert page.count('id="selfos-shared-controls"')==1
        assert page.count('id="privacy-settings"')==1
        assert page.count('let privacySelection')==1
        assert page.count('window.keepCustomStyleTask=true')==1


def test_cached_refresh_preserves_unknown_script_owners_and_has_one_lifecycle():
    from selfos.web.rendering.refresh import refresh_dashboard
    custom="""<script data-selfos-module="custom">const example='data-selfos-module="theme"';function openAppSettings(){return "custom-only";}</script>"""
    page='<html><head></head><body><p>Stored score fixture</p>'+custom+'<script>let isDark=false;const legacyFixture=true;</script></body></html>'
    for _ in range(3):
        page=refresh_dashboard(page)
        assert custom in page
        assert 'Stored score fixture' in page
        assert 'legacyFixture' not in page
        for owner in ('runtime','request','account','settings','theme','jobs','import-settings','usage','publication','quality','overview','staging','onboarding','bootstrap'):
            assert page.count('<script data-selfos-module="'+owner+'"')==1


def test_cached_refresh_upgrades_only_exact_theme_handler_pairs():
    from selfos.web.rendering.refresh import refresh_dashboard
    page='<html><head></head><body><button id="theme-toggle" onclick="toggleTheme()">Theme</button><button id="custom-theme" onclick="toggleTheme()">Custom</button></body></html>'
    page=refresh_dashboard(page)
    assert '<button id="theme-toggle" data-selfos-action="theme.toggle">' in page
    assert '<button id="custom-theme" onclick="toggleTheme()">' in page


def test_cached_refresh_upgrades_exact_job_and_staging_handler_pairs():
    from selfos.web.rendering.refresh import refresh_dashboard
    page='<html><head></head><body><button id="knowledge-btn" onclick="confirmHarvest(false, true)">Build</button><button id="staging-btn" onclick="openStagingModal()">Pending</button><button id="custom-job" onclick="confirmHarvest(false, true)">Custom</button></body></html>'
    page=refresh_dashboard(page)
    assert '<button id="knowledge-btn" data-selfos-action="jobs.knowledge">' in page
    assert '<button id="staging-btn" data-selfos-action="staging.open">' in page
    assert '<button id="custom-job" onclick="confirmHarvest(false, true)">' in page


def test_cached_chat_and_dimension_actions_skip_custom_handlers_and_script_text():
    from selfos.web.rendering.refresh import refresh_dashboard
    custom_script="""<script data-selfos-module="custom">window.buttonExample='<button id="chat-send" onclick="sendChat()">Custom</button>';</script>"""
    outside='<button class="dim-modal-chat" onclick="chatAboutDim()">Custom outside</button>'
    page='<html><head></head><body><div id="chat-panel"><div class="chat-header" onclick="toggleChat()"></div><button id="chat-collapse-btn" onclick="toggleChat(event)"></button><button id="chat-send" onclick="sendChat()"></button></div><div class="grid"><div class="card" data-key="career" onclick="openDim(this)"></div></div>'+outside+custom_script+'</body></html>'
    page=refresh_dashboard(page)
    assert '<div class="chat-header" data-selfos-action="chat.toggle">' in page
    assert '<button id="chat-collapse-btn" data-selfos-action="chat.toggle">' in page
    assert '<button id="chat-send" data-selfos-action="chat.send">' in page
    assert 'data-selfos-action="dimensions.open"' in page
    assert outside in page and custom_script in page
