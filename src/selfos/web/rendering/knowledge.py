"""web / rendering / knowledge responsibilities."""
from selfos.web.rendering.resources import frontend_text, render_ui


def refresh_controls(html):
    """Refresh settings in previously generated dashboards without a new import."""
    import re
    pattern = r'<button class="harvest-btn" onclick="openKnowledgeSettings\(\)"[^>]*>.*?<script>\s*let knowledgeOperation.*?</script>'
    if re.search(pattern, html, flags=re.S):
        html = re.sub(r'<!-- selfos-quality-start -->.*?<!-- selfos-quality-end -->\s*', '', html, flags=re.S)
    return re.sub(pattern, lambda _:CONTROLS.rstrip(),html,count=1,flags=re.S)


CONTROLS = frontend_text('templates/knowledge-quality.html') + frontend_text('templates/import-controls.html')

from selfos.web.rendering.import_status import HTML as PUBLICATION_HTML, SCRIPT as PUBLICATION_SCRIPT
CONTROLS = CONTROLS.replace('<dialog id="knowledge-settings"', PUBLICATION_HTML + '\n<dialog id="knowledge-settings"', 1)
CONTROLS = CONTROLS.replace('<div id="knowledge-domains">', '<p id="import-modal-published" role="status"></p><p id="import-modal-boundary"></p><div id="knowledge-domains">', 1)
CONTROLS = CONTROLS.replace('let knowledgeOperation = null;', 'let knowledgeOperation = null;\n' + PUBLICATION_SCRIPT, 1)
