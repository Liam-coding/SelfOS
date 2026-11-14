"""Canonical knowledge search and evidence browser with packaged translations."""
from selfos.web.rendering.resources import frontend_text, render_ui
import re

from selfos.web.i18n import namespace_messages
LOCALES = namespace_messages('search')

STYLE = frontend_text('templates/knowledge-browser-style.html')

_HTML = frontend_text('templates/knowledge-browser.html')
_HTML = _HTML.replace('</section>','<style data-selfos-corrections>'+frontend_text('styles/knowledge-corrections.css')+'</style></section>',1)

_SCRIPT = frontend_text('scripts/knowledge-corrections.js') + '\n' + frontend_text('scripts/knowledge-browser.js')

HTML = _HTML + ''.join('<script data-selfos-module="'+owner+'" data-selfos-generation="1">'+frontend_text('scripts/'+name)+'</script>' for owner,name in [('corrections','knowledge-corrections.js'),('knowledge','knowledge-browser.js')])


from selfos.web.rendering.timeline import HTML as TIMELINE_HTML
HTML += TIMELINE_HTML
HTML += frontend_text('templates/changes.html').rstrip().replace('<!-- selfos-changes-end -->','<style>'+frontend_text('styles/changes.css')+'</style><script>'+frontend_text('scripts/changes.js')+'</script><!-- selfos-changes-end -->')

def refresh_library(html):
    """Refresh an existing library without regenerating private dashboard data."""
    html = re.sub(r'<!-- selfos-project-timeline-start -->.*?<!-- selfos-project-timeline-end -->', '', html, flags=re.S)
    html = re.sub(r'<!-- selfos-changes-start -->.*?<!-- selfos-changes-end -->\s*', '', html, flags=re.S)
    pattern = r'<section\b[^>]*\bid="knowledge-library"[^>]*>.*?</section>\s*<dialog\b[^>]*\bid="kb-detail"[^>]*>.*?</dialog>\s*<script\b[^>]*>.*?</script>(?:\s*<script\b[^>]*data-selfos-module="knowledge"[^>]*>.*?</script>)?'
    updated, count = re.subn(pattern, lambda _: HTML, html, count=1, flags=re.S)
    if not count:
        return html
    return re.sub(r'<style>\s*\.knowledge-library.*?</style>', lambda _: STYLE,
                  updated, count=1, flags=re.S)
