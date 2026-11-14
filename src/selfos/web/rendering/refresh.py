"""Refresh generated UI on authenticated reads without rebuilding stored data."""
import re
from html.parser import HTMLParser
from html import escape
from selfos.web.i18n import runtime
from selfos.web.rendering.resources import frontend_text


class _OpeningTag(HTMLParser):
    def __init__(self,markup):
        super().__init__();self.attributes={};self.feed(markup)
    def handle_starttag(self,tag,attrs):
        if not self.attributes:self.attributes=dict(attrs)


def _upgrade_scoped_actions(page):
    offsets=[0]
    for line in page.splitlines(keepends=True):offsets.append(offsets[-1]+len(line))
    changes=[]
    identities={
        'theme-toggle':('toggleTheme()','theme.toggle'),'lang-toggle':('toggleLang()','theme.language'),
        'knowledge-btn':('confirmHarvest(false, true)','jobs.knowledge'),
        'harvest-btn':('openHarvestModal()','jobs.open'),'knowledge-stop-btn':('stopKnowledge()','jobs.stop'),
        'progress-done-btn':('location.reload()','jobs.reload'),
        'staging-btn':('openStagingModal()','staging.open'),'staging-apply-btn':('applySelectedStaging()','staging.apply'),
        'chat-collapse-btn':('toggleChat(event)','chat.toggle'),'chat-send':('sendChat()','chat.send'),
    }
    classes={
        ('modal-cancel','harvest-modal'):('closeHarvestModal()','jobs.close'),
        ('modal-confirm modal-confirm-incr','harvest-modal'):('confirmHarvest(false)','jobs.incremental'),
        ('modal-confirm modal-confirm-full','harvest-modal'):('confirmHarvest(true)','jobs.full'),
        ('staging-skip','staging-modal'):('closeStagingModal()','staging.close'),
        ('chat-header','chat-panel'):('toggleChat()','chat.toggle'),
        ('dim-modal-chat','dim-modal'):('chatAboutDim()','dimensions.discuss'),
    }
    void={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    class Tags(HTMLParser):
        def __init__(self):super().__init__(convert_charrefs=False);self.stack=[]
        def handle_starttag(self,tag,attributes):
            attrs=dict(attributes);pair=None
            if tag in ('button','div'):
                pair=identities.get(attrs.get('id'))
                if attrs.get('id')=='knowledge-btn' and attrs.get('onclick')=='confirmHarvest(false,true)':pair=('confirmHarvest(false,true)','jobs.knowledge')
                scopes={parent.get('id') for _,parent in self.stack}
                if pair is None:
                    pair=next((value for (class_name,scope),value in classes.items() if class_name==attrs.get('class') and scope in scopes),None)
                grid=any('grid' in parent.get('class','').split() for _,parent in self.stack)
                if pair is None and tag=='div' and grid and 'card' in attrs.get('class','').split() and attrs.get('data-key') in {'career','work','health','learning','research','life','family'}:
                    pair=('openDim(this)','dimensions.open')
                if pair and attrs.get('onclick')==pair[0]:
                    raw=self.get_starttag_text();line,column=self.getpos();start=offsets[line-1]+column
                    rebuilt='<'+tag+''.join(' '+('data-selfos-action' if key=='onclick' else key) if value is None else ' '+('data-selfos-action' if key=='onclick' else key)+'="'+escape(pair[1] if key=='onclick' else value,quote=True)+'"' for key,value in attributes)+('/>' if raw.endswith('/>') else '>')
                    changes.append((start,start+len(raw),rebuilt))
            if tag not in void:self.stack.append((tag,attrs))
        def handle_endtag(self,tag):
            for index in range(len(self.stack)-1,-1,-1):
                if self.stack[index][0]==tag:del self.stack[index:];break
        def handle_startendtag(self,tag,attributes):
            self.handle_starttag(tag,attributes)
            if self.stack and self.stack[-1][0]==tag:self.stack.pop()
    parser=Tags();parser.feed(page)
    for start,end,replacement in reversed(changes):page=page[:start]+replacement+page[end:]
    return page


def refresh_dashboard(page):
    from selfos.web.rendering import auth, knowledge, model, library, overall, onboarding
    from selfos.web.rendering.legacy_i18n import upgrade_legacy_markup
    page=_upgrade_scoped_actions(upgrade_legacy_markup(page))
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
        owned=owner in ('runtime','request','auth','login','account','settings','theme','jobs','import-settings','usage','publication','quality','overview','staging','onboarding','chat','dimensions','privacy','sparklines','knowledge','corrections','timeline','legacy-dashboard','bootstrap')
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
    remove(r'<!-- selfos-onboarding-start -->.*?<!-- selfos-onboarding-end -->')
    remove(r'<section id="import-publication"[^>]*>.*?</section>')
    remove(r'<!-- selfos-quality-start -->.*?<!-- selfos-quality-end -->')
    for identity in ('project-timeline','kb-detail','knowledge-settings','app-settings','model-settings','auth-change','privacy-settings'):
        remove(r'<dialog id="'+identity+r'"[^>]*>.*?</dialog>')
    for identity in ('model-settings-entry','auth-account-buttons'):
        remove(r'<div id="'+identity+r'"[^>]*>.*?</div>')
    page=re.sub(r'<button[^>]*id="knowledge-settings-entry"[^>]*>.*?</button>','<!--selfos-controls-anchor-->',page,count=1,flags=re.S)
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
    main=scripts['theme']+scripts['jobs']+scripts['staging']+scripts['chat']+scripts['dimensions']+scripts['sparklines']
    controls=auth.account_controls(include_runtime=False,include_lifecycle=False)+model.CONTROLS+onboarding.CONTROLS+main
    if '<!--selfos-controls-anchor-->' in page:page=page.replace('<!--selfos-controls-anchor-->',knowledge.CONTROLS,1)
    else:controls=knowledge.CONTROLS+controls
    page=page.replace('</body>',controls+'</body>',1)
    tokens='<style id="selfos-design-tokens">'+frontend_text('styles/tokens.css')+'</style>'
    page=page.replace('</head>',tokens+runtime()+lifecycle+'</head>',1)
    return page
