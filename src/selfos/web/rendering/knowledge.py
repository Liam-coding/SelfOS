"""web / rendering / knowledge responsibilities."""
from selfos.web.rendering.resources import frontend_text


def refresh_controls(html):
    """Refresh settings in previously generated dashboards without a new import."""
    import re
    return re.sub(r'<button class="harvest-btn" onclick="openKnowledgeSettings\(\)"[^>]*>.*?<script>\s*let knowledgeOperation.*?</script>',
                  lambda _:CONTROLS.rstrip(),html,count=1,flags=re.S)


CONTROLS = frontend_text('templates/import-controls.html')
