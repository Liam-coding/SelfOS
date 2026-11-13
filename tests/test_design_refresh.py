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
