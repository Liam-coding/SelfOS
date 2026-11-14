"""Canonical knowledge search and evidence browser with packaged translations."""
from selfos.web.rendering.resources import frontend_text, render_ui
import re
from html.parser import HTMLParser

from selfos.web.i18n import namespace_messages
LOCALES = namespace_messages('search')

STYLE = frontend_text('templates/knowledge-browser-style.html')

_HTML = frontend_text('templates/knowledge-browser.html')
_HTML = _HTML.replace('</section>','<style data-selfos-corrections>'+frontend_text('styles/knowledge-corrections.css')+'</style></section>',1)

_SCRIPT = frontend_text('scripts/knowledge-corrections.js') + '\n' + frontend_text('scripts/knowledge-browser.js')

HTML = _HTML + ''.join('<script data-selfos-module="'+owner+'" data-selfos-generation="1">'+frontend_text('scripts/'+name)+'</script>' for owner,name in [('corrections','knowledge-corrections.js'),('knowledge','knowledge-browser.js')])


from selfos.web.rendering.timeline import HTML as TIMELINE_HTML
HTML += TIMELINE_HTML

def refresh_library(html):
    """Refresh an existing library without regenerating private dashboard data."""
    html = re.sub(r'<!-- selfos-project-timeline-start -->.*?<!-- selfos-project-timeline-end -->', '', html, flags=re.S)
    def preserve_unknown_scripts(match):
        class OpeningTag(HTMLParser):
            def handle_starttag(self, tag, attrs):
                if tag == 'script':self.owner = dict(attrs).get('data-selfos-module')
        preserved = []
        for script in re.findall(r'<script\b[^>]*>.*?</script>', match['scripts'], re.S):
            tag = OpeningTag();tag.owner = None;tag.feed(script)
            known = tag.owner in ('knowledge', 'corrections')
            legacy = tag.owner is None and any(marker in script for marker in ('window.browseKnowledge', 'function browseKnowledge'))
            if not known and not legacy:preserved.append(script)
        return HTML + ''.join(preserved)
    pattern = r'<section\b[^>]*\bid="knowledge-library"[^>]*>.*?</section>\s*<dialog\b[^>]*\bid="kb-detail"[^>]*>.*?</dialog>(?P<scripts>(?:\s*<script\b[^>]*>.*?</script>){0,2})'
    updated, count = re.subn(pattern, preserve_unknown_scripts, html, count=1, flags=re.S)
    if not count:
        return html
    return re.sub(r'<style>\s*\.knowledge-library.*?</style>', lambda _: STYLE,
                  updated, count=1, flags=re.S)
