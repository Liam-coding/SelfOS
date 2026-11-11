"""web / rendering / overall responsibilities."""


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
    card='<aside class="knowledge-overall" aria-labelledby="overall-title">'+overall+legend+'</aside>'
    html=re.sub(r'<div class="knowledge-orbit"[^>]*>.*?<div class="knowledge-orbit-core">.*?</div>\s*</div>',lambda _:card,html,count=1,flags=re.S)
    if greeting:
        html=html.replace('<div class="knowledge-eyebrow">',greeting[0]+'<div class="knowledge-eyebrow">',1)
    return html


STYLE = r'''<style id="selfos-visual-system">
:root { --bg:#f6f7fb; --text:#192235; --muted:#5f6b83; --surface:rgba(255,255,255,.82); --line:rgba(52,72,112,.1); --blue:#007aff; }
body { background:radial-gradient(ellipse at 8% 0%,#e8f0ff 0,transparent 44%),radial-gradient(ellipse at 95% 12%,#edf1ff 0,transparent 35%),var(--bg); color:var(--text); padding:36px clamp(20px,4vw,72px); }
body > .header,body > .hero,body > .grid,body > .knowledge-overview,body > .footer { max-width:1440px; margin-left:auto; margin-right:auto; }
.header { gap:24px; margin-bottom:30px; }
.brand { font-size:32px; font-weight:750; letter-spacing:-1.6px; color:var(--text); }
.slogan { font-size:12px; color:var(--muted); margin-top:7px; }
.header-btns { flex-wrap:wrap; justify-content:flex-end; gap:8px; }
.header-btns button { min-height:38px; border-radius:12px; padding:9px 13px; font-size:12px; font-weight:550; border-color:var(--line); box-shadow:none; }
.header-btns .harvest-btn,.header-btns .lang-btn,.header-btns .theme-btn { background:var(--surface); color:var(--text); }
.header-btns #knowledge-btn { background:var(--blue); color:white; border-color:transparent; }
button { -webkit-tap-highlight-color:transparent; }
button:focus-visible,.card:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible { outline:3px solid #69aaff; outline-offset:4px; }
.knowledge-overview { position:relative; overflow:hidden; border:1px solid rgba(255,255,255,.85); border-radius:32px; padding:clamp(26px,4vw,54px); background:linear-gradient(130deg,rgba(255,255,255,.97),rgba(247,250,255,.82)); box-shadow:0 24px 70px rgba(37,65,122,.075),inset 0 1px 0 white; margin-bottom:24px; }
.knowledge-overview::after { content:''; position:absolute; width:420px; height:420px; right:-80px; top:-100px; background:radial-gradient(circle,rgba(84,153,255,.16),transparent 65%); pointer-events:none; }
.knowledge-hero-layout { display:grid; grid-template-columns:minmax(0,1fr) 320px; align-items:center; gap:40px; position:relative; z-index:1; }
.knowledge-overall { background:var(--surface); border:1px solid var(--line); border-radius:24px; padding:24px; box-shadow:0 12px 35px rgba(38,65,110,.05); }
.knowledge-overall .overall { gap:12px; }
.knowledge-overall .overall-ring-num { font-size:42px; font-weight:650; letter-spacing:-1.5px; color:var(--text); font-variant-numeric:tabular-nums; }
.knowledge-overall .overall-ring-bg { stroke:var(--line); }
.knowledge-overall .overall-info h2 { font-size:12px; color:var(--muted); font-weight:600; }
.knowledge-overall .overall-status { display:inline-block; border-radius:20px; background:rgba(65,122,210,.08); padding:5px 14px; margin:8px 0; font-size:13px; color:var(--text); }
.knowledge-overall .overall-count,.knowledge-overall .overall-date { font-size:11px; line-height:1.8; color:var(--muted); }
.knowledge-overall .legend { background:transparent; box-shadow:none; border:0; border-top:1px solid var(--line); padding:16px 0 0; margin-top:18px; display:grid; grid-template-columns:1fr 1fr; gap:10px; }
.knowledge-overall .legend-title { grid-column:1 / -1; font-size:10px; color:var(--muted); }
.knowledge-overall .legend-text,.knowledge-overall .legend-range { color:var(--muted); font-size:10px; }
.knowledge-overall .legend-dot { width:6px; height:6px; }
.knowledge-hero-layout .greeting { text-align:left; margin:0 0 12px; font-size:13px; font-weight:500; letter-spacing:0; color:var(--muted); }
.dim-label,.dim-suggestion { color:var(--muted); }
.ring-score { color:var(--text); font-variant-numeric:tabular-nums; }
.grid { gap:16px; }
@media(max-width:1000px) { .knowledge-hero-layout { grid-template-columns:minmax(0,1fr) 280px!important; } }
@media(max-width:700px) { .knowledge-hero-layout { grid-template-columns:1fr!important; } .knowledge-overall { width:100%; } }
.knowledge-eyebrow { display:flex; align-items:center; gap:9px; text-transform:uppercase; letter-spacing:2px; font-size:10px; font-weight:650; color:#6587b7; margin-bottom:18px; }
.knowledge-eyebrow::before { content:''; width:6px; height:6px; background:#438cff; border-radius:50%; box-shadow:0 0 12px #91baff; }
.knowledge-heading { max-width:800px; font-size:clamp(30px,3.4vw,48px); line-height:1.22; letter-spacing:-1.8px; font-weight:650; color:var(--text); }
.knowledge-heading span { background:linear-gradient(105deg,#0877e8,#4e6fec); -webkit-background-clip:text; background-clip:text; color:transparent; }
.knowledge-description { font-size:14px; line-height:1.9; color:var(--muted); margin-top:18px; max-width:600px; text-wrap:balance; }
.knowledge-actions { display:flex; align-items:center; flex-wrap:wrap; gap:12px; margin-top:26px; }
.knowledge-primary,.knowledge-secondary { border:0; border-radius:14px; padding:13px 20px; font-size:13px; font-weight:600; cursor:pointer; transition:transform .2s,box-shadow .2s; }
.knowledge-primary { background:var(--blue); color:white; box-shadow:0 7px 18px rgba(0,122,255,.18); }
.knowledge-secondary { background:rgba(58,99,163,.065); color:#4a648d; }
.knowledge-primary:hover,.knowledge-secondary:hover { transform:translateY(-2px); }
.knowledge-status-line { display:flex; gap:8px; align-items:center; color:var(--muted); font-size:11px; margin-top:18px; min-height:18px; line-height:1.6; }
.knowledge-status-dot { height:5px; width:5px; border-radius:50%; background:#a2aabd; flex-shrink:0; }
.knowledge-status-dot.ready { background:#36aa7c; }
.knowledge-orbit { width:250px; height:250px; display:grid; place-items:center; position:relative; }
.knowledge-orbit svg { position:absolute; width:100%; height:100%; color:#66a8fa; opacity:.65; }
.knowledge-orbit-core { width:128px; height:128px; border-radius:32px; transform:rotate(-9deg); display:grid; place-items:center; background:linear-gradient(135deg,rgba(255,255,255,.95),rgba(214,230,255,.45)); box-shadow:0 20px 45px rgba(58,105,185,.16),inset 0 1px 0 white; border:1px solid rgba(255,255,255,.9); backdrop-filter:blur(18px); }
.knowledge-orbit-core span { transform:rotate(9deg); font-size:37px; letter-spacing:-3px; font-weight:650; color:#3f76c5; }
.knowledge-metrics { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:12px; margin-top:38px; position:relative; z-index:1; }
.knowledge-metric { padding:18px 20px; border-radius:18px; background:rgba(235,241,250,.52); border:1px solid rgba(255,255,255,.85); min-width:0; }
.knowledge-metric-label { color:#74829a; font-size:11px; margin-bottom:7px; }
.knowledge-metric-value { font-size:25px; color:var(--text); font-weight:600; letter-spacing:-.8px; font-variant-numeric:tabular-nums; }
.knowledge-metric-note { font-size:10px; color:#9aa5b7; margin-top:5px; line-height:1.5; }
.hero { border-radius:24px; background:var(--surface); border:1px solid var(--line); padding:24px 28px; margin-bottom:24px; }
.hero-greeting,.hero-overall { min-width:0; }
.greeting { font-size:clamp(21px,2.2vw,30px); color:var(--text); font-weight:500; }
.card { border-radius:22px; background:var(--surface); border:1px solid var(--line); box-shadow:0 3px 16px rgba(38,59,96,.035); padding:24px; transition:transform .2s,box-shadow .2s; }
.card:hover { transform:translateY(-4px); box-shadow:0 12px 30px rgba(38,59,96,.08); }
.sparkline { max-width:100%; }
.modal,.chat-panel { border-radius:24px; box-shadow:0 24px 70px rgba(19,44,88,.15); border:1px solid var(--line); }
.modal-backdrop { background:rgba(31,42,66,.26); backdrop-filter:blur(10px); }
.progress-modal { max-width:580px; }
.progress-log { font-size:11px; line-height:1.8; border-radius:14px; }
#knowledge-settings { background:var(--surface)!important; color:var(--text)!important; border:1px solid var(--line); box-shadow:0 24px 80px rgba(19,44,88,.2); width:min(580px,calc(100vw - 32px)); max-width:580px!important; padding:28px!important; margin:auto; }
#knowledge-settings::backdrop { background:rgba(31,42,66,.26); backdrop-filter:blur(10px); }
#knowledge-settings h3 { font-size:22px; font-weight:600; letter-spacing:-.4px; margin-bottom:14px; }
#knowledge-settings p { font-size:12px; line-height:1.8; margin:16px 0; color:var(--muted); }
#knowledge-domains { display:flex; flex-wrap:wrap; gap:10px; margin:20px 0; }
#knowledge-domains label { background:rgba(80,117,178,.08); border:1px solid var(--line); padding:10px 12px; border-radius:12px; font-size:12px; display:flex; align-items:center; gap:7px; margin:0!important; }
#knowledge-domains input { accent-color:var(--blue); }
#knowledge-settings input[type=text],#knowledge-custom,#knowledge-settings select { background:var(--bg); color:var(--text); border:1px solid var(--line); padding:10px; border-radius:10px; max-width:100%; margin-top:8px; }
#knowledge-custom { display:block; width:100%; }
#knowledge-settings > button { border:1px solid var(--line); background:rgba(80,117,178,.075); color:var(--text); padding:10px 12px; border-radius:10px; font-size:12px; cursor:pointer; margin:4px 2px; }
#knowledge-settings > button:nth-last-child(3) { background:var(--blue); color:white; border-color:transparent; }
#knowledge-settings button:disabled { opacity:.4; cursor:default; }
body.dark { --bg:#101722; --text:#e9eef8; --muted:#8b99af; --surface:rgba(26,36,52,.84); --line:rgba(142,170,216,.13); background:radial-gradient(ellipse at 8% 0%,#18283f,transparent 50%),var(--bg); color:var(--text); }
body.dark .brand,body.dark .greeting { color:var(--text); }
body.dark .knowledge-overview { background:linear-gradient(130deg,#1b2a40,#152236); border-color:rgba(153,185,238,.13); box-shadow:0 24px 70px rgba(0,0,0,.18),inset 0 1px 0 rgba(160,186,224,.05); }
body.dark .knowledge-metric { background:rgba(65,95,145,.16); border-color:rgba(153,185,238,.09); }
body.dark .knowledge-orbit-core { background:linear-gradient(135deg,rgba(82,120,181,.35),rgba(35,61,100,.5)); border-color:rgba(157,194,250,.2); box-shadow:0 20px 45px rgba(0,0,0,.16),inset 0 1px 0 rgba(214,230,255,.12); }
body.dark .knowledge-orbit-core span { color:#96c1ff; }
body.dark .knowledge-secondary { color:#a3b8dd; background:rgba(112,153,225,.11); }
body.dark .card,body.dark .hero { background:var(--surface); border-color:var(--line); }
body.dark .header-btns .harvest-btn,body.dark .header-btns .lang-btn,body.dark .header-btns .theme-btn,body.dark .chat-panel { background:var(--surface); color:var(--text); }
body.dark .header-btns #knowledge-btn { background:var(--blue); color:white; }
@media(max-width:700px) { .knowledge-heading span { display:block; white-space:nowrap; } }
@media(max-width:1000px) { .knowledge-hero-layout { grid-template-columns:minmax(0,1fr) 170px; gap:16px; } .knowledge-orbit { width:170px; height:170px; } .knowledge-orbit-core { width:95px; height:95px; border-radius:25px; } .knowledge-metric { padding:16px 13px; } }
@media(max-width:700px) { body { padding:22px 16px 100px; } .header { align-items:flex-start; gap:20px; flex-direction:column; } .header-right { align-items:flex-start; width:100%; } .header-btns { justify-content:flex-start; } .knowledge-overview { border-radius:24px; padding:28px 22px; } .knowledge-hero-layout { grid-template-columns:1fr; } .knowledge-orbit { display:none; } .knowledge-heading { letter-spacing:-1px; } .knowledge-metrics { grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin-top:26px; } .knowledge-metric:last-child { grid-column:1 / -1; } .knowledge-metric { padding:15px; } .hero { padding:20px; flex-direction:column; gap:22px; } .hero-greeting,.hero-overall { padding:0; justify-content:center; width:100%; } .grid { grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; } .card { padding:18px 12px; min-width:0; } .chat-panel { width:calc(100vw - 32px); max-width:340px; right:16px; bottom:16px; } }
@media(prefers-reduced-motion:reduce) { *,*::before,*::after { animation-duration:.01ms!important; transition-duration:.01ms!important; scroll-behavior:auto!important; } }
/* Shared controls and surfaces, including legacy panels. */
:root { --panel:#fff; --soft:#edf2fa; --shadow:0 20px 60px rgba(37,65,122,.10); --radius:24px; }
body.dark { --panel:#192438; --soft:#202f45; --shadow:0 20px 60px rgba(0,0,0,.26); }
body,button,input,select,textarea { font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
button,input,select,textarea { font-size:13px; }
button { transition:background .18s,border-color .18s,box-shadow .18s; }
:is(body,body.dark) .modal,:is(body,body.dark) .chat-panel { background:var(--panel); color:var(--text); border:1px solid var(--line); border-radius:var(--radius); box-shadow:var(--shadow); }
:is(body,body.dark) .modal { width:min(520px,calc(100vw - 32px)); max-width:520px; padding:28px; max-height:calc(100dvh - 40px); overflow:auto; }
:is(body,body.dark) .modal-title,:is(body,body.dark) .progress-title { font-size:22px; font-weight:650; letter-spacing:-.5px; color:var(--text); }
:is(body,body.dark) .modal-body { color:var(--muted); font-size:13px; line-height:1.8; }
:is(body,body.dark) .modal-icon { width:52px; height:52px; display:grid; place-items:center; margin:0 auto 16px; border-radius:16px; background:var(--soft); font-size:24px; }
:is(body,body.dark) .modal-steps,:is(body,body.dark) .dim-modal-sugg,:is(body,body.dark) .progress-log,:is(body,body.dark) .staging-file-item { background:var(--soft); color:var(--muted); border:1px solid var(--line); border-radius:14px; padding:16px; }
:is(body,body.dark) .modal-steps li,:is(body,body.dark) .staging-file-name { color:var(--text); font-size:13px; font-weight:550; }
:is(body,body.dark) .staging-file-target { color:var(--muted); }
:is(body,body.dark) .modal-cancel,:is(body,body.dark) .staging-skip,:is(body,body.dark) .chat-collapse-btn { color:var(--muted); background:var(--soft); border:1px solid var(--line); }
.modal-actions button,.staging-actions button,.progress-done-btn,.dim-modal-chat { border-radius:12px; min-height:42px; padding:11px 16px; font-size:13px; font-weight:600; }
:is(body,body.dark) .modal-confirm,:is(body,body.dark) .staging-apply-all,:is(body,body.dark) .progress-done-btn,:is(body,body.dark) .dim-modal-chat,:is(body,body.dark) .chat-send { background:var(--blue); color:white; }
:is(body,body.dark) .modal-confirm-full { background:var(--soft); color:var(--text); border:1px solid var(--line); }
.progress-modal { max-width:580px!important; }
:is(body,body.dark) .progress-bar-wrap { background:var(--soft); height:8px; }
.progress-bar-fill { background:var(--blue); }
.progress-log { height:180px; font-size:12px; line-height:1.8; overflow-wrap:anywhere; }
.dim-modal-score { font-size:56px; font-weight:650; letter-spacing:-2px; font-variant-numeric:tabular-nums; }
:is(body,body.dark) .dim-modal-status { color:var(--muted); font-size:13px; }
:is(body,body.dark) .card { background:var(--surface); border-radius:var(--radius); }
:is(body,body.dark) .dim-label { color:var(--muted); font-size:12px; letter-spacing:.06em; margin-bottom:14px; }
:is(body,body.dark) .ring-score { color:var(--text); font-size:26px; font-weight:650; }
:is(body,body.dark) .ring-bg { stroke:var(--line); }
.dim-status { font-size:13px; margin-bottom:8px; }
:is(body,body.dark) .dim-suggestion { font-size:12px; line-height:1.8; color:var(--muted); }
.chat-panel { width:360px; height:min(560px,calc(100dvh - 48px)); }
:is(body,body.dark) .chat-header,:is(body,body.dark) .chat-input-row { border-color:var(--line); padding:16px; }
:is(body,body.dark) .chat-header-title { color:var(--text); font-size:13px; }
:is(body,body.dark) .chat-header-sub { color:var(--muted); }
.chat-messages { padding:18px; gap:12px; }
.msg { font-size:13px; line-height:1.8; border-radius:16px; padding:12px 14px; }
:is(body,body.dark) .msg-ai { background:var(--soft); color:var(--text); }
:is(body,body.dark) .msg-user { background:var(--blue); color:white; }
:is(body,body.dark) .chat-input { background:var(--soft); color:var(--text); border:1px solid var(--line); border-radius:12px; padding:11px 12px; min-width:0; }
.chat-input:focus { border-color:var(--blue)!important; }
.chat-send { border-radius:12px; }
:is(body,body.dark) #knowledge-settings,:is(body,body.dark) #app-settings,:is(body,body.dark) #model-settings,:is(body,body.dark) #kb-detail { background:var(--panel)!important; color:var(--text); border-radius:var(--radius); box-shadow:var(--shadow); border:1px solid var(--line); max-height:calc(100dvh - 40px); overflow:auto; }
#app-settings h3,#model-settings h3,#knowledge-settings h3,.kb-detail-content h2 { font-size:22px; font-weight:650; letter-spacing:-.5px; }
#app-settings p { font-size:13px; line-height:1.8; color:var(--muted); }
#app-settings select,#model-settings input:not([type=checkbox]),#model-settings select,#knowledge-settings input:not([type=checkbox]),#knowledge-settings select { background:var(--soft)!important; color:var(--text); border:1px solid var(--line); padding:11px 12px; border-radius:12px; }
#app-settings button,#model-settings button,#knowledge-settings > button { min-height:42px; border-radius:12px; font-size:13px; padding:11px 16px; }
#app-settings .harvest-btn { background:var(--soft); color:var(--text); border:1px solid var(--line); }
.knowledge-library { box-shadow:0 3px 16px rgba(38,59,96,.035); }
.kb-list .kb-card { background:var(--panel); box-shadow:0 3px 16px rgba(38,59,96,.035); }
.kb-list .kb-card:hover { box-shadow:0 10px 24px rgba(38,59,96,.08); }
.kb-detail-content h3 { font-size:15px; font-weight:600; margin:22px 0 8px; }
.kb-detail-content pre { background:var(--soft); font-size:13px; }
:is(body,body.dark) footer { color:var(--muted); padding:20px 0; font-size:11px; }
@media(max-width:700px) { :is(body,body.dark) .modal { padding:24px 20px; } .modal-actions,.staging-actions { flex-wrap:wrap; } .chat-panel { width:calc(100vw - 32px); max-width:360px; right:16px; bottom:16px; } .grid { grid-template-columns:repeat(2,minmax(0,1fr)); } .dim-label { font-size:11px; } }
@media(prefers-reduced-motion:reduce) { *,*::before,*::after { animation:none!important; transition:none!important; scroll-behavior:auto!important; } }
</style>'''


OVERVIEW = r'''<section class="knowledge-overview" aria-labelledby="knowledge-heading">
  <div class="knowledge-hero-layout">
    <div>
      <div class="knowledge-eyebrow">Personal Intelligence</div>
      <h1 class="knowledge-heading" id="knowledge-heading" data-zh="让你的知识，变得更清晰。" data-en="Your knowledge. A little clearer.">让你的知识，<span>变得更清晰。</span></h1>
      <p class="knowledge-description" data-zh="从日常对话中，留下值得记住的事实、选择和经验。让过去的思考，成为下一步的起点。" data-en="Keep the facts, choices and experience that matter. Turn past thinking into a starting point for what comes next.">从日常对话中，留下值得记住的事实、选择和经验。<br>让过去的思考，成为下一步的起点。</p>
      <div class="knowledge-actions">
        <button class="knowledge-secondary" onclick="browseKnowledge('projects')" data-zh="查看知识" data-en="Browse knowledge">查看知识</button>
        <button class="knowledge-primary" onclick="confirmHarvest(false,true)" data-zh="整理我的知识" data-en="Organize my knowledge">整理我的知识 <span aria-hidden="true">↗</span></button>
        <button class="knowledge-secondary" onclick="openKnowledgeSettings()" data-zh="关注哪些内容" data-en="Choose what matters">关注哪些内容</button>
      </div>
      <div class="knowledge-status-line" aria-live="polite"><span class="knowledge-status-dot" id="knowledge-connection-dot"></span><span id="knowledge-overview-status">正在连接本地知识库…</span></div>
    </div>
    <div class="knowledge-orbit" aria-hidden="true">
      <svg viewBox="0 0 250 250" fill="none"><circle cx="125" cy="125" r="109" stroke="currentColor" stroke-opacity=".3"/><circle cx="125" cy="125" r="89" stroke="currentColor" stroke-opacity=".35" stroke-dasharray="2 8"/><path d="M30 180L218 64M36 60L216 181" stroke="currentColor" stroke-opacity=".18"/><circle cx="214" cy="62" r="7" fill="#94bfff" stroke="white" stroke-width="3"/><circle cx="31" cy="180" r="5" fill="#91a9ec"/><circle cx="194" cy="209" r="4" fill="#88bbf4"/></svg>
      <div class="knowledge-orbit-core"><span>Self</span></div>
    </div>
  </div>
  <div class="knowledge-metrics">
    <div class="knowledge-metric"><div class="knowledge-metric-label" data-zh="项目" data-en="Projects">项目</div><div class="knowledge-metric-value" id="knowledge-count-cards">—</div><div class="knowledge-metric-note" data-zh="目标与下一步" data-en="Goals and next steps">目标与下一步</div></div>
    <div class="knowledge-metric"><div class="knowledge-metric-label" data-zh="可复用经验" data-en="Experience">可复用经验</div><div class="knowledge-metric-value" id="knowledge-count-lessons">—</div><div class="knowledge-metric-note" data-zh="让思考持续积累" data-en="Thinking that compounds">让思考持续积累</div></div>
    <div class="knowledge-metric"><div class="knowledge-metric-label" data-zh="个人事实" data-en="Personal facts">个人事实</div><div class="knowledge-metric-value" id="knowledge-count-personal_facts">—</div><div class="knowledge-metric-note" data-zh="来自你的明确表达" data-en="Explicitly shared by you">来自你的明确表达</div></div>
    <div class="knowledge-metric"><div class="knowledge-metric-label" data-zh="偏好" data-en="Preferences">偏好</div><div class="knowledge-metric-value" id="knowledge-count-preferences">—</div><div class="knowledge-metric-note" data-zh="保留当前的选择" data-en="Your current choices">保留当前的选择</div></div>
    <div class="knowledge-metric"><div class="knowledge-metric-label" data-zh="历史" data-en="History">历史</div><div class="knowledge-metric-value" id="knowledge-count-history">—</div><div class="knowledge-metric-note" data-zh="变化与来源可追溯" data-en="Changes with a source">变化与来源可追溯</div></div>
  </div>
</section>
<script>
async function updateKnowledgeOverview() {
  const status = document.getElementById('knowledge-overview-status');
  try {
    const response = await fetch('/__knowledge_settings__');
    if (!response.ok) throw new Error('Knowledge service unavailable');
    const data = await response.json();
    for (const key of ['cards','lessons','personal_facts','preferences','history']) {
      document.getElementById('knowledge-count-' + key).textContent = data.counts[key] || 0;
    }
    document.getElementById('knowledge-connection-dot').classList.add('ready');
    const english = document.documentElement.lang === 'en' || localStorage.getItem('selfos-lang') === 'en';
    status.textContent = data.saved_checkpoints
      ? (english ? data.saved_checkpoints + ' saved conversation parts · Original sources preserved' : '已保存 ' + data.saved_checkpoints + ' 个对话片段 · 原文保留，可继续整理')
      : (english ? 'Local knowledge · Sources and backups preserved' : '本地知识库 · 保留来源与备份');
  } catch (error) {
    document.getElementById('knowledge-connection-dot').classList.remove('ready');
    status.textContent = '暂时无法连接本地服务，请检查服务是否启动。';
  }
}
document.addEventListener('DOMContentLoaded', updateKnowledgeOverview);
</script>'''
