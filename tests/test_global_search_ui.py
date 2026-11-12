import json
import shutil
import subprocess

from selfos.web.rendering import library


def test_search_client_default_filters_highlights_retry_and_language(tmp_path):
    from selfos.web.i18n import runtime
    script = runtime().split('<script',1)[1].split('>',1)[1].split('</script>',1)[0] + library.HTML.split('<script>', 1)[1].split('</script>', 1)[0]
    node = shutil.which('node')
    assert node, 'Node is required for JavaScript regression testing'
    harness = r'''
const elements=new Map(),events=new Map();
class Element {
 constructor(tag='div'){this.tagName=tag;this.children=[];this.dataset={};this.value='';this._text='';this.hidden=false;this.disabled=false;this.open=false;this.handlers={};}
 set id(value){this._id=value;elements.set(value,this);} get id(){return this._id;}
 set textContent(value){this._text=String(value);this.children=[];} get textContent(){return this._text+this.children.map(c=>c.textContent||'').join('');}
 set innerHTML(value){throw Error('Untrusted HTML must not be rendered');}
 append(...children){this.children.push(...children);} appendChild(child){this.append(child);return child;}
 replaceChildren(...children){this._text='';this.children=children;}
 setAttribute(key,value){this[key]=value;} removeAttribute(key){delete this[key];}
 addEventListener(key,handler){this.handlers[key]=handler;}
 querySelector(){return new Element();} querySelectorAll(){return this.children;}
 showModal(){this.open=true;} close(){this.open=false;this.handlers.close?.();} focus(){document.activeElement=this;}
 scrollIntoView(){} remove(){}
}
global.document={documentElement:{lang:'en'},activeElement:null,
 getElementById(id){if(!elements.has(id)){const el=new Element();el.id=id;}return elements.get(id);},
 createElement(tag){return new Element(tag);},createTextNode(text){const el=new Element('#text');el.textContent=text;return el;},
 querySelector(selector){return this.getElementById(selector==='.kb-tabs'?'kb-tabs':selector);},
 querySelectorAll(){return this.getElementById('kb-tabs').children;},
 addEventListener(key,handler){if(!events.has(key))events.set(key,[]);events.get(key).push(handler);}};
global.window=global;global.localStorage={getItem:()=>null,setItem(){}};document.dispatchEvent=e=>{for(const fn of events.get(e.type)||[])fn(e);};global.matchMedia=()=>({matches:true});
const row={id:'record1',category:'preferences',title:'Concise updates',summary:'Prefer atomic updates',
 match_excerpt:'Snippet atomic <img src=x>',match_ranges:[[8,14]],match_field:'summary',
 project_contexts:[{id:'project1',title:'Alpha'}],source_count:0,missing_source_count:1,
 date:'2026-11-10',kind:'user_fact',source_scope:'record'};
const fixture={items:[row],total:2,counts:{preferences:2},filtered_counts:{preferences:2},
 filters:{projects:[{id:'project1',title:'Alpha'}],sources:['codex']}};
let urls=[],failMore=true;
global.fetch=async url=>{urls.push(String(url));const params=new URL(url,'http://fixture').searchParams;
 if(String(url).startsWith('/__knowledge_corrections__'))return {ok:true,json:async()=>({actions:[]})};
 if(params.get('offset')==='1'&&failMore){failMore=false;return {ok:false,json:async()=>({code:'unavailable',error:'backend error'})};}
 return {ok:true,json:async()=>fixture};};
SCRIPT
const el=id=>document.getElementById(id),tick=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 for(const handler of events.get('DOMContentLoaded')||[])handler();await tick();
 if(new URL(urls[0],'http://fixture').searchParams.get('category')!=='all')throw Error('Search must default to all categories');
 if(!el('kb-list').textContent.includes('Snippet atomic <img src=x>'))throw Error('Actual match excerpt missing');
 if(!el('kb-status').textContent.includes('Showing 1 of 2 records')||!el('kb-list').textContent.includes('0 sources'))throw Error('Localized counts were not interpolated');
 el('kb-project').value='project1';el('kb-source-filter').value='codex';el('kb-date-from').value='2026-11-10';
 el('kb-project').onchange();await tick();
 const searchRequests=()=>urls.filter(url=>url.startsWith('/__knowledge__?'));
 const params=new URL(searchRequests().at(-1),'http://fixture').searchParams;
 if(params.get('project')!=='project1'||params.get('source')!=='codex'||params.get('date_from')!=='2026-11-10')throw Error('Filters not sent');
 el('kb-more').onclick();await tick();
 if(el('kb-more').hidden||el('kb-more').disabled)throw Error('Failed pagination must be retryable');
 el('kb-more').onclick();await tick();
 if(new URL(searchRequests().at(-1),'http://fixture').searchParams.get('offset')!=='1')throw Error('Failed page skipped');
 el('kb-search').value='atomic';el('kb-search').focus();selfosI18n.setLocale('zh');
 for(const handler of events.get('selfos-language')||[])handler();await tick();
 if(el('kb-search').value!=='atomic'||el('kb-project').value!=='project1'||document.activeElement!==el('kb-search'))throw Error('Translation changed user input or focus');
 let sourceAttempt=0;
 global.fetch=async url=>{
  if(String(url).startsWith('/__knowledge_item__'))return {ok:true,json:async()=>({item:{...row,kind:'inference',decisions:[],blockers:[],next_steps:[],missing_source_count:0},sources:[{id:'doc1',source:'uploaded_file',role:'document',file:'report.txt'}],source_count:1})};
  sourceAttempt++;if(sourceAttempt===1)return {ok:false,json:async()=>({code:'source_missing',error:'backend English must not be shown'})};
  return {ok:true,json:async()=>({text:sourceAttempt===2?'part':'tail',text_total:8,next_offset:sourceAttempt===2?4:null})};
 };
 el('kb-list').children[0].onclick();await tick();
 const sourceButton=()=>el('kb-sources').children[0].children.find(child=>child.tagName==='button');
 sourceButton().onclick();await tick();
 if(!el('kb-sources').textContent.includes('原始来源已丢失或移动'))throw Error('Source error must be localized');
 sourceButton().onclick();await tick();sourceButton().onclick();await tick();
 if(!el('kb-sources').textContent.includes('parttail'))throw Error('Original source pages missing');
 selfosI18n.setLocale('en');for(const handler of events.get('selfos-language')||[])handler();
 if(!el('kb-sources').textContent.includes('parttail'))throw Error('Language switch discarded original text');
 console.log('search UI passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    harness = harness.replace('SCRIPT', script)
    path=tmp_path/'search.js';path.write_text(harness,encoding='utf-8')
    result = subprocess.run([node, str(path)], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr


def test_search_strings_are_packaged_and_complete_in_both_languages():
    assert library.LOCALES['en'].keys() == library.LOCALES['zh'].keys()
    assert 'All knowledge' in library.LOCALES['en'].values()
    assert 'id="kb-project"' in library.HTML and 'id="kb-date-to"' in library.HTML


def test_cached_library_refresh_preserves_surrounding_content():
    old = '<style>.knowledge-library{color:red}</style><header>Existing private dashboard</header>'
    old += '<section id="knowledge-library">old search</section><dialog id="kb-detail">old detail</dialog><script>oldSearch();</script>'
    old += '<main>Existing scores and notes</main>'
    updated = library.refresh_library(old)
    assert 'Existing private dashboard' in updated and 'Existing scores and notes' in updated
    assert 'oldSearch' not in updated and 'id="kb-project"' in updated
    assert updated.count("const categories=['all','projects','lessons','personal_facts','preferences','history']") == 1
    assert 'const searchLocales' not in updated
    assert library.refresh_library(updated) == updated
