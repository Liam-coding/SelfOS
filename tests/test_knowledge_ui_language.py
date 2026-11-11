from selfos.web.rendering.knowledge import CONTROLS, refresh_controls

def test_refresh_legacy_settings_preserves_surrounding_dashboard_and_is_idempotent():
    old='<button class="harvest-btn" onclick="openKnowledgeSettings()">整理设置</button><dialog id="knowledge-settings">legacy</dialog><script>let knowledgeOperation = null; legacy();</script>'
    page='<header>'+old+'</header><main>Personal dashboard</main>'
    updated=refresh_controls(page)
    assert updated=='<header>'+CONTROLS.rstrip()+'</header><main>Personal dashboard</main>'
    assert refresh_controls(updated)==updated
    assert updated.count('let knowledgeOperation')==1
