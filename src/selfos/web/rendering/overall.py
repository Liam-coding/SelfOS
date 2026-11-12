"""web / rendering / overall responsibilities."""
from selfos.web.rendering.resources import frontend_text, render_ui


def integrate_overall(html):
    """Move existing score content into the knowledge hero without changing data."""
    import re
    if 'class="knowledge-overall"' in html: return html
    start=html.find('<div class="hero">'); end=html.find('<div class="grid">',start)
    if start<0 or end<0: return html
    hero=html[start:end]
    begin=hero.find('<div class="overall">'); finish=hero.rfind('  </div>')
    if begin<0 or finish<begin: return html
    overall=hero[begin:finish].strip()
    greeting=re.search(r'<div class="greeting".*?</div>',hero,re.S)
    html=html[:start]+html[end:]
    legend_start=html.find('<div class="legend">'); legend_end=html.find('<footer>',legend_start)
    legend=''
    if legend_start>=0 and legend_end>legend_start:
        legend=html[legend_start:legend_end].strip();html=html[:legend_start]+html[legend_end:]
    card='<a class="knowledge-overall" href="#dimension-cards" aria-labelledby="overall-title">'+overall+legend+'</a>'
    html=html.replace('<div class="grid">', '<div class="grid" id="dimension-cards" tabindex="-1">', 1)
    html=re.sub(r'<div class="knowledge-orbit"[^>]*>.*?<div class="knowledge-orbit-core">.*?</div>\s*</div>',lambda _:card,html,count=1,flags=re.S)
    if greeting:
        html=html.replace('<div class="knowledge-eyebrow">',greeting[0]+'<div class="knowledge-eyebrow">',1)
    return html


STYLE = frontend_text('templates/visual-system.html')


OVERVIEW = frontend_text('templates/overview.html')
