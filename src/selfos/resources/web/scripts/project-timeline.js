
(function(window){'use strict';window.selfosUI.register('timeline',()=>{
 const requests=new Set(),cleanups=[],sourceActions=new WeakMap();let draft=null,ignoreClose=0,pendingMore=false;
 function on(node,type,callback){node.addEventListener(type,callback);cleanups.push(()=>node.removeEventListener(type,callback));}
 async function ownedFetch(url,options={}){const controller=new AbortController();requests.add(controller);try{const response=await fetch(url,{...options,signal:controller.signal});const data=await response.json();return {ok:response.ok,status:response.status,json:async()=>data};}finally{requests.delete(controller);}}
 const el=id=>document.getElementById(id),t=(key,values={})=>window.selfosI18n.t(window.selfosI18n.has('timeline.'+key)?'timeline.'+key:'timeline.unknown',values);
 const bind=(element,text)=>{window.selfosI18n.bindText(element,'ui.common.value',()=>({value:text()}));return element;};
 const node=(tag,text,cls)=>{const n=document.createElement(tag);if(typeof text==='function')bind(n,text);else if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
 let active='',generation=0,offset=0,total=0,items=[],current=null,busy=false,failed=false,revision='',resetNotice=false;
 const originals=new Map(),sourceNext=new Map(),sourceTotals=new Map(),sourceBusy=new Set(),sourceErrors=new Set();
 const status=c=>t(c.status==='completed'&&c.verified?'verified_complete':(window.selfosI18n.has('timeline.'+c.status)?c.status:'unknown'));
 function listField(holder,key,values){if(values?.length){holder.append(node('h4',()=>t(key)));const list=node('ul');for(const text of values)list.append(node('li',text));holder.append(list);}}
 function render(){
  bind(el('pt-heading'),()=>t('title'));bind(el('pt-close'),()=>t('close'));bind(el('pt-note'),()=>t('note'));bind(el('pt-filter-label'),()=>t('filter'));
  const category=el('pt-filter').value||'all';el('pt-filter').replaceChildren();for(const key of ['all','goals','decisions','progress','blockers']){const option=node('option',()=>t(key));option.value=key;el('pt-filter').append(option);}el('pt-filter').value=category;
  el('pt-current').replaceChildren();if(current){el('pt-current').append(node('h3',()=>t('current')+' · '+current.title),node('p',current.intent),node('p',()=>status(current),'pt-meta'),node('p',()=>t('observation')+': '+(current.observed_at?window.selfosI18n.date(current.observed_at):t('unknown')),'pt-meta'));for(const key of ['decisions','blockers','next_steps'])listField(el('pt-current'),key,current[key]);}
  el('pt-list').replaceChildren();let unknown=false;
  for(const entry of items){if(entry.ordering_basis==='unknown'&&!unknown){el('pt-list').append(node('h3',()=>t('unknown_group')));unknown=true;}
   const row=node('article',undefined,'pt-milestone');row.append(node('h3',()=>t(entry.type)),node('p',entry.type==='progress'?()=>status(entry):entry.text));
   for(const [key,value]of [['event',entry.event_time],['observation',entry.observed_at],['source',entry.source_times],['import',entry.imported_at]])row.append(node('p',()=>t(key)+': '+(Array.isArray(value)?value.map(time=>window.selfosI18n.date(time)).join(' · ')||t('unknown'):value?window.selfosI18n.date(value):t('unknown')),'pt-meta'));
   row.append(node('p',()=>t('basis',{basis:t(entry.ordering_basis)}),'pt-meta'),node('p',()=>t(entry.source_scope==='project_context'?'legacy':'context'),'pt-meta'));
   if(entry.superseded)row.append(node('p',()=>t('superseded')));if(entry.type==='progress')for(const key of ['blockers','next_steps'])listField(row,key,entry[key]);
   if(entry.unavailable_source_count)row.append(node('p',()=>t('missing',{count:entry.unavailable_source_count}),'pt-meta'));
   for(const source of entry.sources){const key=entry.id+':'+source.id;row.append(node('p',()=>[window.selfosI18n.has('search.source_'+source.source)?window.selfosI18n.t('search.source_'+source.source):source.source,source.timestamp?window.selfosI18n.date(source.timestamp):'',source.file].filter(Boolean).join(' · '),'pt-meta'));
    const button=node('button',()=>t(sourceErrors.has(key)?'retry':originals.has(key)?'more_source':'source_button'));button.disabled=sourceBusy.has(key);button.dataset.selfosAction='timeline.source';sourceActions.set(button,async()=>{const seq=generation;sourceBusy.add(key);sourceErrors.delete(key);render();try{const r=await ownedFetch('/__knowledge_source__?'+new URLSearchParams({id:source.id,offset:sourceNext.get(key)||0,limit:24000}));const d=await r.json();if(!r.ok)throw Error('source');if(seq===generation){originals.set(key,(originals.get(key)||'')+d.text);sourceNext.set(key,d.next_offset??null);sourceTotals.set(key,d.text_total??Array.from(originals.get(key)).length);}}catch(e){if(seq===generation)sourceErrors.add(key);}finally{if(seq===generation){sourceBusy.delete(key);render();}}});
    if(originals.has(key))row.append(node('pre',originals.get(key)),node('p',()=>t('source_page',{shown:Array.from(originals.get(key)).length,total:sourceTotals.get(key)}),'pt-meta'));if(!originals.has(key)||sourceNext.get(key)!==null)row.append(button);if(sourceErrors.has(key))row.append(node('p',()=>t('source_error')));
   }el('pt-list').append(row);
  }
  bind(el('pt-status'),()=>busy?t('loading'):failed?t('error'):(resetNotice?t('updated')+' ':'')+(items.length?t('count',{shown:items.length,total}):t('empty')));
  bind(el('pt-more'),()=>t('more'));el('pt-more').disabled=busy;el('pt-more').hidden=offset>=total||failed;bind(el('pt-retry'),()=>t('retry'));el('pt-retry').hidden=!failed;el('pt-retry').disabled=busy;
  document.querySelectorAll('[data-project-timeline]').forEach(button=>bind(button,()=>t('open')));
 }
 async function load(more=false){pendingMore=more;const seq=++generation;if(!more){offset=0;items=[];total=0;revision='';resetNotice=false;}busy=true;failed=false;render();try{const r=await ownedFetch('/__knowledge_timeline__?'+new URLSearchParams({id:active,category:el('pt-filter').value,offset,limit:20,revision}));const d=await r.json();if(!r.ok)throw Error('timeline');if(seq!==generation)return;if(d.reset_required){items=[];offset=0;resetNotice=true;}current=d.current;revision=d.revision||'';items.push(...d.items);offset=(d.offset??offset)+d.items.length;total=d.total;}catch(e){if(seq===generation)failed=true;}finally{if(seq===generation){busy=false;render();}}}

 function label(){return t('open');}
 async function open(id){active=id;current=null;items=[];offset=0;total=0;originals.clear();sourceNext.clear();sourceTotals.clear();sourceErrors.clear();sourceBusy.clear();el('pt-filter').value='all';if(!el('project-timeline').open)el('project-timeline').showModal();await load();}
 function action(event){const button=event.target.closest?.('[data-selfos-action]');if(!button||!document.contains(button)||!button.closest('#project-timeline'))return;const actions={'timeline.more':['click',()=>load(true)],'timeline.retry':['click',()=>load(true)],'timeline.filter':['change',()=>load()],'timeline.close':['click',()=>el('project-timeline').close()],'timeline.source':['click',()=>sourceActions.get(button)?.()]};if(!Object.hasOwn(actions,button.dataset.selfosAction)||actions[button.dataset.selfosAction][0]!==event.type)return;event.preventDefault();actions[button.dataset.selfosAction][1]();}
 function init(){++generation;ignoreClose=0;on(document,'click',action);on(document,'change',action);on(el('project-timeline'),'close',()=>{if(ignoreClose){--ignoreClose;return;}++generation;busy=false;});const state=draft;draft=null;if(state){el('pt-filter').value=state.filter;if(state.open){const dialog=el('project-timeline');if(dialog.open){++ignoreClose;dialog.close();}dialog.showModal();}}render();if(state?.pending&&active)load(state.more);}
 function teardown(){draft={filter:el('pt-filter').value,open:el('project-timeline').open,pending:busy,more:pendingMore};++generation;busy=false;for(const controller of requests)controller.abort();requests.clear();sourceBusy.clear();cleanups.splice(0).reverse().forEach(cleanup=>cleanup());}
 return {open,refresh:load,label,init,teardown,busy:()=>requests.size>0};
},{dependencies:['request','locale'],roots:['#project-timeline']});
for(const [name,method]of Object.entries({openProjectTimeline:'open',projectTimelineLabel:'label'}))if(!window[name])window[name]=(...args)=>window.selfosUI.module('timeline')[method](...args);
})(window);
