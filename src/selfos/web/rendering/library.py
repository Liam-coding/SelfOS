"""web / rendering / library responsibilities."""


STYLE = r'''<style>
.knowledge-library{margin:28px 0;padding:28px;border:1px solid var(--line);border-radius:28px;background:var(--surface)}
.knowledge-library h2{font-size:25px;margin:0 0 8px}.knowledge-library p{color:var(--muted)}
.kb-toolbar,.kb-tabs{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}
.kb-tabs button,.kb-more,.kb-close,.kb-source{border:1px solid var(--line);border-radius:12px;padding:10px 14px;background:var(--surface);color:var(--text);cursor:pointer}
.kb-tabs button[aria-pressed=true]{background:var(--blue);color:white}.kb-search{width:100%;box-sizing:border-box;border:1px solid var(--line);border-radius:12px;padding:12px;color:var(--text);background:var(--surface)}
.kb-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.kb-card{width:100%;text-align:left;padding:20px;border:1px solid var(--line);border-radius:18px;background:var(--surface);color:var(--text);cursor:pointer;overflow-wrap:anywhere}
.kb-card:hover{border-color:var(--blue)}.kb-card strong{display:block;font-size:17px}.kb-card p{line-height:1.6;white-space:pre-wrap}.kb-meta{font-size:12px;color:var(--muted)}
#kb-detail{width:min(720px,calc(100vw - 32px));max-height:85vh;box-sizing:border-box;border:1px solid var(--line);border-radius:24px;padding:28px;background:var(--bg);color:var(--text)}
#kb-detail::backdrop{background:rgba(10,20,40,.4);backdrop-filter:blur(8px)}.kb-close{float:right}.kb-detail-content{clear:both;overflow-wrap:anywhere;line-height:1.7}.kb-detail-content pre{white-space:pre-wrap;border:1px solid var(--line);padding:14px;border-radius:12px;font:inherit;max-height:340px;overflow:auto}.kb-source-row{border-top:1px solid var(--line);padding:14px 0}.kb-more{margin-top:16px}
@media(max-width:700px){.knowledge-library{padding:20px}.kb-list{grid-template-columns:1fr}#kb-detail{padding:20px}}
</style>'''


HTML = r'''<section id="knowledge-library" class="knowledge-library" aria-labelledby="kb-heading">
<h2 id="kb-heading" data-zh="你的知识，随时可查" data-en="Your knowledge, within reach">你的知识，随时可查</h2>
<p data-zh="当前知识与变化历史分开保存。每条内容都可以回到来源。" data-en="Current knowledge and history are separate. Follow each record to its source.">当前知识与变化历史分开保存。每条内容都可以回到来源。</p>
<div class="kb-tabs" aria-label="Knowledge categories"></div><input class="kb-search" id="kb-search" type="search" maxlength="500" aria-label="搜索知识" placeholder="搜索项目、选择或经验…">
<p id="kb-status" role="status" aria-live="polite">正在加载知识…</p><div class="kb-list" id="kb-list"></div><button id="kb-more" class="kb-more" hidden>加载更多</button>
</section><dialog id="kb-detail" aria-label="知识详情"><button class="kb-close" autofocus>关闭</button><div class="kb-detail-content" id="kb-detail-content"></div></dialog>
<script>
(() => {
 const labels={projects:['项目','Projects'],lessons:['可复用经验','Experience'],personal_facts:['个人事实','Personal facts'],preferences:['偏好','Preferences'],history:['历史','History']};
 const el=id=>document.getElementById(id),t=(zh,en)=>document.documentElement.lang==='en'?en:zh;
 const attribution=item=>{
   if(item.category==='history'&&item.original_category==='project_state')return t('历史项目状态 · 保留当时的上下文','Historical project state · Earlier context preserved');
   if(item.category==='lessons'&&item.support_review==='summary_model_review')return t('经验推断 · 已对照候选摘要复核','Method inference · Compared with candidate summaries');
   if(item.category==='history'&&item.source_scope==='summary_context')return t('项目观察 · 来源于归并摘要','Project observation · From sourced summaries');
   if(item.category==='projects'){
     if(item.status==='completed')return item.verified?t('已核验完成','Verified complete'):t('完成待核验','Completion unverified');
     const statuses={in_progress:['进行中','In progress'],blocked:['待解决阻碍','Blocked'],paused:['已暂停','Paused'],reported_complete:['助手报告完成，未核验','Assistant reports completion; unverified'],unknown:['状态未确认','Status unknown']};
     return t(...(statuses[item.status]||statuses.unknown));
   }
   const kinds={user_fact:['用户明确表达','Explicit user statement'],assistant_suggestion:['AI 建议','AI suggestion'],inference:['归纳推断','Inference']};
   return t(...(kinds[item.kind]||kinds.inference));
 };
 let category='projects',offset=0,generation=0,timer,activeId='',sourceOffset=0,detailGeneration=0;
 const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
 const request=async path=>{const r=await fetch(path);const d=await r.json();if(!r.ok)throw new Error(d.error||t('暂时无法读取知识','Knowledge unavailable'));return d;};
 async function load(more=false){
 const seq=++generation;if(!more){offset=0;el('kb-list').replaceChildren();}el('kb-more').hidden=true;el('kb-status').textContent=t('正在加载…','Loading…');
 document.querySelectorAll('.kb-tabs button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.category===category)));
 try{const d=await request('/__knowledge__?'+new URLSearchParams({category,query:el('kb-search').value,offset,limit:20}));if(seq!==generation)return;
 for(const item of d.items){const b=node('button',undefined,'kb-card');b.append(node('strong',item.title),node('p',item.summary),node('span',[attribution(item),item.date.slice(0,10),t(item.source_count+' 个来源',item.source_count+' sources'),item.conflict?t('存在冲突','Conflicting records'):t('查看依据','View evidence')].filter(Boolean).join(' · '),'kb-meta'));b.onclick=()=>open(item.id);el('kb-list').append(b);}
 offset+=d.items.length;el('kb-status').textContent=d.total?t('找到 '+d.total+' 条内容','Found '+d.total+' records'):t(el('kb-search').value?'没有匹配内容，请换个关键词。':'这个分类还没有内容；整理后会自动出现在这里。',el('kb-search').value?'No matches. Try another search.':'This category is empty. Organizing adds supported records.');el('kb-more').hidden=offset>=d.total;
 }catch(e){if(seq===generation)el('kb-status').textContent=e.message;}}
 async function sources(initial=null){const seq=detailGeneration,id=activeId,more=el('kb-more-sources');if(more.disabled)return;more.disabled=true;try{const d=initial||await request('/__knowledge_item__?'+new URLSearchParams({id,source_offset:sourceOffset}));if(seq!==detailGeneration)return;
 const holder=el('kb-sources');for(const s of d.sources){const row=node('div',undefined,'kb-source-row');row.append(node('div',[s.source,s.role,s.timestamp,s.file].filter(Boolean).join(' · '),'kb-meta'));const b=node('button',t('读取来源原文','Read original source'),'kb-source');b.onclick=async()=>{b.disabled=true;try{const raw=await request('/__knowledge_source__?'+new URLSearchParams({id:s.id}));row.append(node('pre',raw.text));b.remove();}catch(e){row.append(node('p',e.message));b.disabled=false;}};row.append(b);holder.append(row);}sourceOffset+=d.sources.length;el('kb-more-sources').hidden=sourceOffset>=d.source_count;
 }catch(e){if(seq===detailGeneration)el('kb-sources').append(node('p',e.message));}finally{if(seq===detailGeneration)more.disabled=false;}}
 async function open(id){activeId=id;sourceOffset=0;const seq=++detailGeneration,content=el('kb-detail-content');content.replaceChildren(node('p',t('加载详情…','Loading details…')));el('kb-detail').showModal();try{const d=await request('/__knowledge_item__?'+new URLSearchParams({id}));if(seq!==detailGeneration)return;const item=d.item;content.replaceChildren(node('h2',item.title),node('p',attribution(item),'kb-meta'),node('p',item.summary));if(item.conflict)content.append(node('p',t('存在冲突，需结合来源确认。','Conflicting records: check sources.')));
 for(const [field,zh,en]of [['decisions','当前选择','Current decisions'],['blockers','待解决','Blockers'],['next_steps','下一步','Next steps']])if(item[field].length){content.append(node('h3',t(zh,en)));const list=node('ul');item[field].forEach(v=>list.append(node('li',v)));content.append(list);}
 if(item.category==='projects'){const timeline=node('button',window.projectTimelineLabel(),'pt-entry-button');timeline.dataset.projectTimeline=id;timeline.onclick=()=>window.openProjectTimeline(id);content.append(timeline);}
 if(item.evidence)content.append(node('h3',t('原文依据','Quoted evidence')),node('pre',item.evidence));
 if(item.source_scope==='project_context')content.append(node('p',t('这是归档的项目记录。旧记录仅保留项目上下文来源，无法确定这条记录的直接依据与时间。','Archived project record. Legacy sources describe project context; direct evidence and event time are unavailable.')));
 if(item.source_scope==='session_context')content.append(node('p',t('来源属于讨论这条记录的会话；日期为来源会话时间。','Sources belong to the conversation discussing this record; the date is the session time.')));
 if(item.source_scope==='summary_context')content.append(node('p',item.category==='lessons'
   ? t('这条经验基于摘要推断；查看原始对话确认细节与适用范围。','Based on summarized evidence; check the original conversation for detail and scope.')
   : t('这是有来源的项目观察。归并依据是已保存摘要，尚未逐条核验原文；可查看来源确认细节与适用范围。','This project observation comes from saved summaries. Raw evidence has not been independently rechecked; inspect sources for detail and scope.')));
 content.append(node('h3',t('来源 · '+d.source_count,'Sources · '+d.source_count)));const holder=node('div');holder.id='kb-sources';const b=node('button',t('更多来源','More sources'),'kb-more');b.id='kb-more-sources';b.onclick=()=>sources();content.append(holder,b);await sources(d);
 }catch(e){if(seq===detailGeneration)content.replaceChildren(node('p',e.message));}}
 function tabs(){const holder=document.querySelector('.kb-tabs');holder.replaceChildren();for(const [key,value]of Object.entries(labels)){const b=node('button',t(...value));b.dataset.category=key;b.onclick=()=>{category=key;load();};holder.append(b);}el('kb-search').placeholder=t('搜索项目、选择或经验…','Search projects, decisions or experience…');el('kb-search').setAttribute('aria-label',t('搜索知识','Search knowledge'));el('kb-more').textContent=t('加载更多','Load more');el('kb-detail').querySelector('.kb-close').textContent=t('关闭','Close');}
 window.browseKnowledge=key=>{if(labels[key])category=key;load();el('knowledge-library').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});};
 el('kb-detail').querySelector('.kb-close').onclick=()=>el('kb-detail').close();el('kb-detail').addEventListener('close',()=>{detailGeneration++;});
 el('kb-search').oninput=()=>{generation++;clearTimeout(timer);timer=setTimeout(()=>load(),250);};el('kb-more').onclick=()=>load(true);
 document.addEventListener('DOMContentLoaded',()=>{tabs();load();});document.addEventListener('selfos-language',()=>{tabs();load();});
})();
</script>'''

from selfos.web.rendering.timeline import HTML as TIMELINE_HTML
HTML += TIMELINE_HTML


def refresh_library(page):
    """Refresh an existing library component without writing generated dashboard data."""
    import re
    page = re.sub(r'<!-- selfos-project-timeline-start -->.*?<!-- selfos-project-timeline-end -->', '', page, flags=re.S)
    pattern = r'<section id="knowledge-library"(?=[\s>]).*?</section>\s*<dialog id="kb-detail"(?=[\s>]).*?</dialog>\s*<script>.*?</script>'
    page = re.sub(pattern, lambda _: HTML, page, count=1, flags=re.S)
    return page
