import re
from selfos.web.i18n import catalogs
from selfos.web.rendering.resources import frontend_text


def test_browser_uses_shared_keys_without_language_triggered_reload():
    source=frontend_text('scripts/knowledge-browser.js')
    template=frontend_text('templates/knowledge-browser.html')
    assert "document.documentElement.lang==='en'?en:zh" not in source
    assert "selfos-language',()=>{tabs();load();}" not in source
    assert 'data-zh' not in template and 'data-en' not in template
    assert 'bindText' in source
    messages=catalogs()['locales']['en']['messages']
    for key in re.findall(r"['\"](ui\.[a-zA-Z0-9_.]+)['\"]",source+template):assert key in messages


def test_browser_retains_tabs_pagination_details_and_original_source_on_switch(tmp_path):
    import shutil,subprocess
    from selfos.web.i18n import runtime
    common=runtime().split('<script',1)[1].split('>',1)[1].split('</script>',1)[0]
    script=frontend_text('scripts/ui-runtime.js')+"selfosUI.register('request',()=>({}));selfosUI.register('locale',()=>selfosI18n);selfosUI.register('corrections',()=>({history(){},mount(){}}));selfosUI.register('timeline',()=>({}));"+frontend_text('scripts/knowledge-browser.js')
    harness=r"""
const elements=new Map(),listeners=new Map(),fixed={'kb-search-form':'search','kb-project':'filter','kb-source-filter':'filter','kb-date-from':'filter','kb-date-to':'filter','kb-reset':'reset','kb-more':'more','kb-retry':'retry','kb-close':'close'};
class Element{
 constructor(tag='div'){this.tag=tag;this.dataset={};this.attributes={};this.children=[];this.textContent='';this.value='';this.disabled=false;this.isConnected=true;}
 set id(v){this._id=v;elements.set(v,this);if(fixed[v])this.dataset.selfosAction='knowledge.'+fixed[v];}get id(){return this._id;}
 append(...nodes){for(const node of nodes){node.parent=this;this.children.push(node);}}replaceChildren(...nodes){this.children=[];this.append(...nodes);}setAttribute(k,v){this.attributes[k]=v;}
 querySelector(selector){return selector==='.kb-close'?get('close'):null;}addEventListener(k,f){if(!this.listeners)this.listeners={};this.listeners[k]=f;}
 click(){document.dispatchEvent({type:'click',target:this,preventDefault(){}});}closest(selector){return selector==='[data-selfos-action]'?this:get('knowledge-library');}focus(){}
 showModal(){this.open=true;}close(){this.open=false;if(this.listeners?.close)this.listeners.close();}remove(){this.isConnected=false;if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);}scrollIntoView(){}
}
function get(id){if(!elements.has(id)){const element=new Element();element.id=id;}return elements.get(id);}
const tabs=get('kb-tabs');
global.window=global;global.localStorage={getItem:()=>null,setItem(){}};global.matchMedia=()=>({matches:true});
global.document={documentElement:{lang:'en'},getElementById:get,contains:()=>true,createElement:tag=>new Element(tag),createTextNode:text=>Object.assign(new Element('#text'),{textContent:text}),querySelector:s=>s==='.kb-tabs'?tabs:null,querySelectorAll:s=>s==='.kb-tabs button'?tabs.children:[],addEventListener:(k,f)=>{if(!listeners.has(k))listeners.set(k,[]);listeners.get(k).push(f);},dispatchEvent:e=>{for(const f of listeners.get(e.type)||[])f(e);}};
const item={id:'fixture',category:'projects',title:'Literal project',summary:'Literal summary',status:'in_progress',date:'2026-01-02',source_count:1234,decisions:['Literal decision'],blockers:[],next_steps:[],source_scope:'session_context'};
const detail={item,sources:[{id:'source-fixture',source:'codex',role:'user',timestamp:'2026-01-02T08:00:00Z',file:'fixture.jsonl'}],source_count:1234};
let calls=[],finishDetail,finishSource;
global.fetch=async(path)=>{calls.push(path);const url=new URL(path,'http://fixture');if(url.pathname==='/__knowledge__')return {ok:true,json:async()=>({items:[item],total:41})};if(url.pathname==='/__knowledge_item__')return await new Promise(resolve=>finishDetail=()=>resolve({ok:true,json:async()=>detail}));if(url.pathname==='/__knowledge_source__')return await new Promise(resolve=>finishSource=()=>resolve({ok:true,json:async()=>({text:'Literal original <source>'})}));throw Error(path);};
COMMON
BROWSER
const flush=async()=>{for(let n=0;n<30;n++)await Promise.resolve();};
const descend=(element,predicate)=>{for(const child of element.children){if(predicate(child))return child;const found=descend(child,predicate);if(found)return found;}return null;};
(async()=>{
selfosUI.init(document);await flush();
const tab=tabs.children[0],card=get('kb-list').children[0],meta=card.children[3];
if(!meta.textContent.includes('1,234')||calls.length!==1)throw Error('Initial list/count wrong');
get('kb-search').value='unsaved query';selfosI18n.setLocale('zh');
if(calls.length!==1||tabs.children[0]!==tab||get('kb-list').children[0]!==card||get('kb-search').value!=='unsaved query'||meta.textContent.includes('In progress'))throw Error('Switch replaced list/tabs/state or retained labels');
get('kb-more').click();await flush();if(new URL(calls[1],'http://fixture').searchParams.get('offset')!=='1')throw Error('Pagination reset on language switch');
card.click();await flush();const before=calls.length;selfosI18n.setLocale('en');if(calls.length!==before||!get('kb-detail').open||!get('kb-detail-content').children[0].textContent.includes('Loading details'))throw Error('Pending detail disturbed');
finishDetail();await flush();
const content=get('kb-detail-content'),heading=content.children[0],sourceButton=descend(content,e=>e.className==='kb-source');
sourceButton.click();await flush();const pendingSource=descend(content,e=>e.className==='kb-source');const sourceCalls=calls.length;selfosI18n.setLocale('zh');if(calls.length!==sourceCalls||!pendingSource.disabled||descend(content,e=>e.className==='kb-source')!==pendingSource||content.children[0]!==heading)throw Error('Pending source disturbed');
finishSource();await flush();const raw=descend(content,e=>e.tag==='pre');if(raw.textContent!=='Literal original <source>')throw Error('Original source altered');
selfosI18n.setLocale('en');if(raw.textContent!=='Literal original <source>'||heading.textContent!=='Literal project'||calls.length!==sourceCalls)throw Error('Source/detail changed or rerequested');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    path=tmp_path/'browser.js';path.write_text(harness.replace('COMMON',common).replace('BROWSER',script),encoding='utf-8')
    result=subprocess.run([shutil.which('node'),str(path)],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stderr
