"""Canonical knowledge search and evidence browser with packaged translations."""
from selfos.web.rendering.resources import frontend_text, render_ui
import json
import re
from importlib.resources import files

LOCALES = {language: json.loads(files('selfos.resources').joinpath(
    'locales', folder, 'search.json').read_text(encoding='utf-8'))
    for language, folder in [('en', 'en'), ('zh', 'zh-CN')]}

STYLE = frontend_text('templates/knowledge-browser-style.html')

_HTML = frontend_text('templates/knowledge-browser.html')

_SCRIPT = frontend_text('scripts/knowledge-browser.js')

HTML = _HTML + '<script>\nconst searchLocales = ' + json.dumps(LOCALES, ensure_ascii=True) + ';\n' + _SCRIPT + '</script>'


from selfos.web.rendering.timeline import HTML as TIMELINE_HTML
HTML += TIMELINE_HTML

def refresh_library(html):
    """Refresh an existing library without regenerating private dashboard data."""
    html = re.sub(r'<!-- selfos-project-timeline-start -->.*?<!-- selfos-project-timeline-end -->', '', html, flags=re.S)
    pattern = r'<section\b[^>]*\bid="knowledge-library"[^>]*>.*?</section>\s*<dialog\b[^>]*\bid="kb-detail"[^>]*>.*?</dialog>\s*<script>.*?</script>'
    updated, count = re.subn(pattern, lambda _: HTML, html, count=1, flags=re.S)
    if not count:
        return html
    return re.sub(r'<style>\s*\.knowledge-library.*?</style>', lambda _: STYLE,
                  updated, count=1, flags=re.S)
