"""Refresh generated UI on authenticated reads without rebuilding stored data."""
import re
from html.parser import HTMLParser
from selfos.web.i18n import runtime
from selfos.web.rendering.resources import frontend_text


class _OpeningTag(HTMLParser):
    def __init__(self,markup):
        super().__init__();self.attributes={};self.feed(markup)
    def handle_starttag(self,tag,attrs):
        if not self.attributes:self.attributes=dict(attrs)


def _upgrade_theme_actions(page):
    def upgrade(match):
        tag=match[0];attrs=_OpeningTag(tag).attributes
        pair={'theme-toggle':('toggleTheme()','theme.toggle'),'lang-toggle':('toggleLang()','theme.language')}.get(attrs.get('id'))
        if not pair or attrs.get('onclick')!=pair[0]:return tag
        for quote in ('"',"'"):
            tag=tag.replace('onclick='+quote+pair[0]+quote,'data-selfos-action="'+pair[1]+'"')
        return tag
    return re.sub(r'<button [^>]*>',upgrade,page)


def refresh_dashboard(page):
    from selfos.web.rendering import auth, knowledge, model, library, overall, onboarding
    from selfos.web.rendering.legacy_i18n import upgrade_legacy_markup
    page=_upgrade_theme_actions(upgrade_legacy_markup(page))
    # Retire the script owned by an old search shell even if its implementation
    # predates today's global entry point. Preserve unrelated cached scripts.
    page=re.sub(r'<section\b[^>]*\bid="knowledge-library"[^>]*>.*?</section>\s*<dialog\b[^>]*\bid="kb-detail"[^>]*>.*?</dialog>\s*<script\b[^>]*>.*?</script>',
                '<!--selfos-library-anchor-->',page,count=1,flags=re.S)
    page=re.sub(r'<style>\s*\.knowledge-library.*?</style>',lambda _:library.STYLE,page,count=1,flags=re.S)
    def strip_script(match):
        script=match[0]
        markers=('id="selfos-i18n"', 'let isDark', 'let knowledgeOperation',
                 'function openAppSettings', 'window.browseKnowledge',
                 'function updateKnowledgeOverview', 'function authRequest', 'const selfosFetch', 'window.openProjectTimeline', 'let privacySelection')
        owner=_OpeningTag(script).attributes.get('data-selfos-module')
        owned=owner in ('runtime','request','account','settings','theme','legacy-dashboard','bootstrap')
        if owner is not None and not owned:return script
        return '' if owned or any(marker in script for marker in markers) else script
    page=re.sub(r'<script\b[^>]*>.*?</script>',strip_script,page,flags=re.S)
    def remove(pattern):
        nonlocal page
        page=re.sub(pattern,'',page,flags=re.S)
    aside=re.search(r'<(?P<overall_tag>aside|a) class="knowledge-overall"[^>]*>.*?</(?P=overall_tag)>',page,re.S)
    greeting=re.search(r'<div class="greeting"[^>]*>.*?</div>',page,re.S)
    page=re.sub(r'<section class="knowledge-overview"[^>]*>.*?</section>','<!--selfos-overview-anchor-->',page,count=1,flags=re.S)
    page=re.sub(r'<section id="knowledge-library"[^>]*>.*?</section>','<!--selfos-library-anchor-->',page,count=1,flags=re.S)
    remove(r'<!-- selfos-project-timeline-start -->.*?<!-- selfos-project-timeline-end -->')
    remove(r'<!-- selfos-changes-start -->.*?<!-- selfos-changes-end -->')
    remove(r'<!-- selfos-onboarding-start -->.*?<!-- selfos-onboarding-end -->')
    remove(r'<!-- selfos-uploads-start -->.*?<!-- selfos-uploads-end -->')
    remove(r'<section id="import-publication"[^>]*>.*?</section>')
    remove(r'<!-- selfos-quality-start -->.*?<!-- selfos-quality-end -->')
    for identity in ('project-timeline','kb-detail','knowledge-settings','app-settings','model-settings','auth-change','privacy-settings'):
        remove(r'<dialog id="'+identity+r'"[^>]*>.*?</dialog>')
    for identity in ('model-settings-entry','auth-account-buttons'):
        remove(r'<div id="'+identity+r'"[^>]*>.*?</div>')
    page=re.sub(r'<button\b[^>]*onclick="openKnowledgeSettings\(\)"[^>]*>.*?</button>','<!--selfos-controls-anchor-->',page,count=1,flags=re.S)
    page=page.replace(auth.STYLE,'')
    overview=overall.OVERVIEW
    if aside:
        overview=re.sub(r'<div class="knowledge-orbit"[^>]*>.*?<div class="knowledge-orbit-core">.*?</div>\s*</div>',lambda _:aside[0],overview,count=1,flags=re.S)
        if greeting:overview=overview.replace('<div class="knowledge-eyebrow" data-i18n="ui.overview.eyebrow">',greeting[0]+'<div class="knowledge-eyebrow" data-i18n="ui.overview.eyebrow">',1)
    # Keep the existing score cards/overall data, inserting current empty UI shells.
    body_start=page.find('>',page.find('<body'))+1
    missing=''
    for anchor,component in [('<!--selfos-overview-anchor-->',overview),('<!--selfos-library-anchor-->',library.HTML)]:
        if anchor in page:page=page.replace(anchor,component,1)
        else:missing+=component
    if body_start>0:page=page[:body_start]+missing+page[body_start:]
    page=overall.integrate_overall(page)
    remove(r'<style id="selfos-shared-controls">.*?</style>')
    remove(r'<style id="selfos-design-tokens">.*?</style>')
    page=re.sub(r'<style id="selfos-visual-system">.*?</style>',lambda _:overall.STYLE,page,count=1,flags=re.S)
    template=frontend_text('templates/dashboard-page.html')
    scripts={_OpeningTag(match[0]).attributes.get('data-selfos-module'):match[0] for match in re.finditer(r'<script\b[^>]*>.*?</script>',template,re.S) if 'data-selfos-module=' in match[0]}
    lifecycle=''.join(scripts[identity] for identity in ('runtime','request','bootstrap'))
    main=scripts['theme']+scripts['legacy-dashboard']
    controls=auth.account_controls(include_runtime=False,include_lifecycle=False)+model.CONTROLS+onboarding.CONTROLS+main
    if '<!--selfos-controls-anchor-->' in page:page=page.replace('<!--selfos-controls-anchor-->',knowledge.CONTROLS,1)
    else:controls=knowledge.CONTROLS+controls
    page=page.replace('</body>',controls+'</body>',1)
    tokens='<style id="selfos-design-tokens">'+frontend_text('styles/tokens.css')+'</style>'
    page=page.replace('</head>',tokens+runtime()+lifecycle+'</head>',1)
    return page
