import shutil
import subprocess


def test_timeline_resources_and_cached_dashboard_refresh():
    from selfos.web.rendering import timeline, library
    assert timeline.LOCALES["en"].keys() == timeline.LOCALES["zh"].keys()
    assert "Project timeline" in timeline.LOCALES["en"].values()
    page = '<header>Private scores</header><section id="knowledge-library">old</section><dialog id="kb-detail"></dialog><script>window.browseKnowledge=function(){};</script><main>Notes</main>'
    updated = library.refresh_library(page)
    assert "Private scores" in updated and "Notes" in updated
    assert "oldLibrary" not in updated
    assert updated.count('id="project-timeline"') == 1
    assert library.refresh_library(updated) == updated


def test_actual_timeline_script_handles_filters_sources_retries_and_language(tmp_path):
    from selfos.web.rendering.timeline import HTML
    from selfos.web.i18n import runtime
    from selfos.web.rendering.resources import frontend_text
    script = runtime().split('<script',1)[1].split('>',1)[1].split('</script>',1)[0] + frontend_text('scripts/ui-runtime.js') + "selfosUI.register('request',()=>({}));selfosUI.register('locale',()=>selfosI18n);" + frontend_text('scripts/project-timeline.js')
    harness = r"""
const elements=new Map(),events=new Map(),fixed={'pt-close':'close','pt-filter':'filter','pt-more':'more','pt-retry':'retry'};
class Element {
 constructor(tag='div'){this.tagName=tag;this.children=[];this.dataset={};this.value='all';this._text='';this.hidden=false;this.disabled=false;this.open=false;this.handlers={};}
 set id(v){this._id=v;elements.set(v,this);if(fixed[v])this.dataset.selfosAction='timeline.'+fixed[v];}get id(){return this._id;}
 set textContent(v){this._text=String(v);this.children=[];}get textContent(){return this._text+this.children.map(c=>c.textContent||'').join('');}
 set innerHTML(v){throw Error('Unsafe HTML rendering');}
 append(...v){this.children.push(...v);}replaceChildren(...v){this._text='';this.children=v;}
 setAttribute(k,v){this[k]=v;}addEventListener(k,v){this.handlers[k]=v;}
 click(){document.dispatchEvent({type:'click',target:this,preventDefault(){}});}change(){document.dispatchEvent({type:'change',target:this,preventDefault(){}});}closest(selector){return selector==='[data-selfos-action]'?this:document.getElementById('project-timeline');}
 showModal(){this.open=true;}close(){this.open=false;this.handlers.close?.();}focus(){}
}
global.document={contains:()=>true,documentElement:{lang:'en'},getElementById(id){if(!elements.has(id)){const e=new Element();e.id=id;}return elements.get(id);},createElement(t){return new Element(t);},querySelectorAll(){return [];},addEventListener(k,h){events.set(k,h);}};
global.window=global;global.localStorage={getItem:()=>null,setItem(){}};document.dispatchEvent=e=>events.get(e.type)?.(e);let urls=[],fail=true;
const entry={id:'e1',type:'goals',text:'Goal <img src=x>',status:'',blockers:[],next_steps:[],event_time:'',observed_at:'2026-01-01',source_times:['2026-01-01'],imported_at:'',ordering_basis:'observation',source_scope:'session_context',superseded:false,sources:[{id:'s1',source:'codex',file:'session.jsonl',timestamp:'2026-01-01'}],unavailable_source_count:1};
global.fetch=async url=>{urls.push(String(url));if(String(url).includes('__knowledge_source__')){const offset=new URL(url,'http://test').searchParams.get('offset');return {ok:true,json:async()=>offset==='24000'?{text:' retained tail',text_total:24014,next_offset:null}:{text:'Original <script>text</script>'.padEnd(24000,'x'),text_total:24014,next_offset:24000}};}
 if(new URL(url,'http://test').searchParams.get('offset')==='1'&&fail){fail=false;return {ok:false,json:async()=>({error:'SECRET PATH'})};}
 return {ok:true,json:async()=>({revision:'a'.repeat(64),current:{title:'Alpha',intent:'Current goal',status:'blocked',blockers:['Missing adapter'],next_steps:[],decisions:[],observed_at:'2026-01-03',verified:false},items:[entry],total:2})};};
SCRIPT
const el=id=>document.getElementById(id),tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 selfosUI.init(document);await window.openProjectTimeline('project1');await tick();
 if(!el('project-timeline').open||!el('pt-current').textContent.includes('Current goal'))throw Error('Current state missing');
 if(!el('pt-list').textContent.includes('Goal <img src=x>'))throw Error('Safe milestone missing');
 if(!el('pt-list').textContent.includes('Event time: Unknown')||!el('pt-list').textContent.includes('Import time: Unknown'))throw Error('Unknown times missing');
 el('pt-more').click();await tick();if(el('pt-retry').disabled||el('pt-retry').hidden)throw Error('Retry unavailable');
 if(el('pt-status').textContent.includes('SECRET'))throw Error('Leaked error');
 el('pt-retry').click();await tick();if(new URL(urls.at(-1),'http://test').searchParams.get('offset')!=='1')throw Error('Skipped failed page');
 el('pt-filter').value='blockers';el('pt-filter').change();await tick();
 if(new URL(urls.at(-1),'http://test').searchParams.get('category')!=='blockers')throw Error('Filter missing');
 const source=el('pt-list').children[0].children.find(c=>c.tagName==='button');await source.click();await tick();
 if(!el('pt-list').textContent.includes('Original <script>text</script>'))throw Error('Original missing');
 const moreSource=el('pt-list').children[0].children.find(c=>c.tagName==='button');if(!moreSource)throw Error('Paginated original was silently truncated');await moreSource.click();await tick();
 if(!el('pt-list').textContent.includes('retained tail')||new URL(urls.at(-1),'http://test').searchParams.get('offset')!=='24000')throw Error('Source continuation missing');
 const priorCurrent=el('pt-current').children[0],priorSource=el('pt-list').children[0];selfosI18n.setLocale('zh');if(el('pt-current').children[0]!==priorCurrent||el('pt-list').children[0]!==priorSource)throw Error('Language switch replaced timeline DOM');
 if(el('pt-filter').value!=='blockers'||!el('pt-list').textContent.includes('Original <script>text</script>'))throw Error('Language discarded state');
 global.fetch=async url=>{urls.push(String(url));return {ok:true,json:async()=>({revision:'b'.repeat(64),reset_required:true,offset:0,current:{title:'Alpha',intent:'Updated goal',status:'paused',decisions:[],blockers:[],next_steps:[]},items:[{...entry,id:'new',text:'New older observation'}],total:1})};};
 el('pt-more').click();await tick();
 if(new URL(urls.at(-1),'http://test').searchParams.get('revision')!=='a'.repeat(64))throw Error('Revision not sent');
 if(el('pt-list').children.length!==1||!el('pt-list').textContent.includes('New older observation'))throw Error('Changed history was appended instead of restarted');
 el('pt-close').click();if(el('project-timeline').open)throw Error('Close failed');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    node = shutil.which('node')
    assert node
    path=tmp_path/'timeline.js';path.write_text(harness.replace('SCRIPT',script),encoding='utf-8')
    result = subprocess.run([node, str(path)], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
