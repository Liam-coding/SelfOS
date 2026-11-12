
(() => {
 const el=id=>document.getElementById(id);
 const tr=(key,values={})=>window.selfosI18n.t(window.selfosI18n.has('search.'+key)?'search.'+key:'search.error_unavailable',values);
 const bound=(element,content)=>{window.selfosI18n.bindText(element,'ui.common.value',()=>({value:content()}));return element;};
 const node=(tag,text,cls)=>{const n=document.createElement(tag);if(typeof text==='function')bound(n,text);else if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
 const named=(prefix,value)=>window.selfosI18n.has('search.'+prefix+value)?tr(prefix+value):value;
 const contextTitle=context=>context.title_known===false?tr('unknown_project',{id:context.id.slice(0,8)}):context.title;
 const categories=['all','projects','lessons','personal_facts','preferences','history'];
 let category='all',offset=0,generation=0,timer,total=0,items=[],counts={},filters={projects:[],sources:[]},loading=false,listError='';
 let activeId='',detailGeneration=0,detailCache=null,detailSources=[],sourceOffset=0,sourcePages=new Map(),sourceListLoading=false,sourceListError='';
 const tabs=new Map();
 const errorText=error=>tr('error_'+(error.code||'unavailable'));
 const request=async path=>{
   let response,data;
   try{response=await fetch(path,{cache:'no-store'});data=await response.json();}catch(error){throw {code:'unavailable'};}
   if(!response.ok)throw {code:data.code||'unavailable'};
   return data;
 };
 function attribution(item){
   if(item.category==='history'&&item.original_category==='project_state')return tr('historical_state');
   if(item.category==='lessons'&&item.support_review==='summary_model_review')return tr('method_review');
   if(item.category==='history'&&item.source_scope==='summary_context')return tr('project_observation');
   if(item.category==='projects')return item.status==='completed'?tr(item.verified?'verified_complete':'completion_unverified'):tr('status_'+(item.status||'unknown'));
   return tr('kind_'+(item.kind||'inference'));
 }
 function highlight(text,ranges){
   const p=node('p'),chars=Array.from(String(text)),valid=(ranges||[]).filter(r=>Array.isArray(r)&&Number.isInteger(r[0])&&Number.isInteger(r[1])&&r[0]>=0&&r[1]>r[0]&&r[1]<=chars.length).sort((a,b)=>a[0]-b[0]);
   let cursor=0;
   for(const [start,end]of valid){if(start<cursor)continue;p.append(document.createTextNode(chars.slice(cursor,start).join('')),node('mark',chars.slice(start,end).join('')));cursor=end;}
   p.append(document.createTextNode(chars.slice(cursor).join('')));return p;
 }
 function updateTabs(){
   const sum=Object.values(counts).reduce((a,b)=>a+b,0);
   for(const key of categories){let button=tabs.get(key);if(!button){button=node('button');button.type='button';button.dataset.category=key;button.onclick=()=>{category=key;clearTimeout(timer);load();};tabs.set(key,button);el('kb-tabs').append(button);}
     bound(button,()=>tr(key)+(counts[key]!==undefined||key==='all'?' ('+window.selfosI18n.number(key==='all'?Object.values(counts).reduce((a,b)=>a+b,0):counts[key])+')':''));button.setAttribute('aria-pressed',String(category===key));}
 }
 function selectOptions(id,options,emptyLabel){
   const select=el(id),value=select.value,oldLabel=Array.from(select.options||select.children).find(o=>o.value===value)?.textContent;
   const empty=node('option',()=>tr(emptyLabel));empty.value='';const nodes=[empty];
   for(const item of options){const option=node('option',item.title);option.value=item.id;nodes.push(option);}
   if(value&&!options.some(item=>item.id===value)){const option=node('option',oldLabel||value);option.value=value;nodes.push(option);}
   select.replaceChildren(...nodes);select.value=value;
 }
 function updateFilters(){
   selectOptions('kb-project',filters.projects.map(context=>({...context,title:()=>contextTitle(context)})),'all_projects');
   selectOptions('kb-source-filter',filters.sources.map(value=>({id:value,title:()=>named('source_',value)})),'all_sources');
   el('kb-date-hint').hidden=!el('kb-date-from').value&&!el('kb-date-to').value;bound(el('kb-date-hint'),()=>tr('date_hint'));
 }
 function renderResults(){
   const focused=document.activeElement?.dataset?.recordId;el('kb-list').replaceChildren();
   for(const item of items){const button=node('button',undefined,'kb-card');button.type='button';button.dataset.recordId=item.id;
     button.append(node('span',()=>tr(item.category),'kb-category'),node('strong',item.title),highlight(item.match_excerpt??item.summary??'',item.match_ranges));
     if(item.match_field)button.append(node('p',()=>tr('match',{field:tr('field_'+item.match_field)}),'kb-meta'));
     if(item.project_contexts?.length)button.append(node('p',()=>tr('context',{projects:item.project_contexts.map(contextTitle).join(' · ')}),'kb-meta'));
     button.append(node('span',()=>[attribution(item),item.date?window.selfosI18n.date(item.date):tr('undated'),tr('source_count',{count:item.source_count||0}),item.conflict?tr('conflict'):tr('view_evidence')].join(' · '),'kb-meta'));
     button.onclick=()=>openDetail(item.id);el('kb-list').append(button);if(item.id===focused)button.focus();}
   renderStatus();
 }
 function renderStatus(){
   bound(el('kb-status'),()=>loading?tr('loading'):listError?errorText({code:listError}):total?tr('found',{shown:items.length,total}):tr('empty'));
   bound(el('kb-more'),()=>tr(listError?'retry':'more'));bound(el('kb-retry'),()=>tr('retry'));
 }
 async function load(more=false){
   const seq=++generation,requestedOffset=more?offset:0;loading=true;listError='';el('kb-retry').hidden=true;
   if(!more){items=[];offset=0;el('kb-more').hidden=true;renderResults();}
   el('kb-more').disabled=true;el('kb-list').setAttribute('aria-busy','true');updateTabs();renderStatus();
   try{
     const data=await request('/__knowledge__?'+new URLSearchParams({category,query:el('kb-search').value,project:el('kb-project').value,source:el('kb-source-filter').value,date_from:el('kb-date-from').value,date_to:el('kb-date-to').value,offset:requestedOffset,limit:20}));
     if(seq!==generation)return;
     items=more?items.concat(data.items):data.items;offset=requestedOffset+data.items.length;total=data.total;counts=data.filtered_counts||{};filters=data.filters||filters;
     loading=false;updateTabs();updateFilters();renderResults();el('kb-more').hidden=offset>=total;
   }catch(error){if(seq!==generation)return;loading=false;listError=error.code||'unavailable';renderStatus();el('kb-more').hidden=!more;el('kb-retry').hidden=more;}
   finally{if(seq===generation){el('kb-more').disabled=false;el('kb-list').setAttribute('aria-busy','false');}}
 }
 function renderSources(){
   const holder=el('kb-sources');if(!holder)return;holder.replaceChildren();
   for(const source of detailSources){const row=node('div',undefined,'kb-source-row'),page=sourcePages.get(source.id);
     const sourceLabel=()=>[named('source_',source.source),named('role_',source.role),source.timestamp?window.selfosI18n.date(source.timestamp):'',source.file].filter(Boolean).join(' · ');
     row.append(node('div',sourceLabel,'kb-meta'));
     if(page?.loaded){row.append(node('pre',page.text),node('p',()=>tr('source_page',{shown:Array.from(page.text).length,total:page.total}),'kb-meta'));}
     if(page?.error)row.append(node('p',()=>errorText({code:page.error})));
     if(!page?.loaded||page.next!==null){const button=node('button',()=>tr(page?.loading?'loading':page?.error?'retry':page?.loaded?'more_source_text':'read_source'),'kb-source');button.type='button';button.disabled=!!page?.loading;button.onclick=()=>readOriginal(source.id);row.append(button);}
     holder.append(row);
   }
   const more=el('kb-more-sources');if(more){more.hidden=sourceOffset>=(detailCache?.source_count||0);more.disabled=sourceListLoading;bound(more,()=>tr(sourceListError?'retry':'more_sources'));}
   if(sourceListError)holder.append(node('p',()=>errorText({code:sourceListError})));
 }
 async function readOriginal(id){
   const seq=detailGeneration;let page=sourcePages.get(id);if(!page){page={text:'',next:0,total:0,loaded:false};sourcePages.set(id,page);}if(page.loading)return;
   page.loading=true;page.error='';renderSources();
   try{const data=await request('/__knowledge_source__?'+new URLSearchParams({id,offset:page.next||0,limit:24000}));if(seq!==detailGeneration)return;
     page.text+=data.text;page.total=data.text_total??Array.from(page.text).length;page.next=data.next_offset??null;page.loaded=true;
   }catch(error){if(seq===detailGeneration)page.error=error.code||'unavailable';}
   finally{if(seq===detailGeneration){page.loading=false;renderSources();}}
 }
 async function moreSources(){
   if(sourceListLoading)return;const seq=detailGeneration;sourceListLoading=true;sourceListError='';renderSources();
   try{const data=await request('/__knowledge_item__?'+new URLSearchParams({id:activeId,source_offset:sourceOffset}));if(seq!==detailGeneration)return;
     detailSources.push(...data.sources);sourceOffset+=data.sources.length;
   }catch(error){if(seq===detailGeneration)sourceListError=error.code||'unavailable';}
   finally{if(seq===detailGeneration){sourceListLoading=false;renderSources();}}
 }
 function renderDetail(){
   if(!detailCache)return;const item=detailCache.item,content=el('kb-detail-content');
   content.replaceChildren(node('h2',item.title),node('p',()=>tr(item.category)+' · '+attribution(item),'kb-meta'),node('p',item.summary));
   if(item.conflict)content.append(node('p',()=>tr('conflict')));
   if(item.scope_type){
     content.append(node('p',()=>tr('preference_scope',{scope:named('scope_',item.scope_type)})+(item.scope_type==='activity'||item.scope_type==='project'?' · '+item.scope:''),'kb-meta'));
     if(item.scope_type==='unknown')content.append(node('p',()=>tr('preference_scope_unknown_note')));
   }
   if(item.superseded_by_source_ids?.length)content.append(node('p',()=>tr('preference_superseded')));
   if(item.valid_from)content.append(node('p',()=>tr('preference_valid_from',{date:item.valid_from})));
   if(item.valid_until)content.append(node('p',()=>tr('preference_valid_until',{date:item.valid_until})));
   if(item.revision?.evidence)content.append(node('h3',()=>tr('preference_revision_evidence')),node('pre',item.revision.evidence));
   if(item.validity_evidence&&item.validity_evidence!==item.revision?.evidence)content.append(node('h3',()=>tr('preference_revision_evidence')),node('pre',item.validity_evidence));
   if(item.user_corrected)content.append(node('p',()=>tr('preference_user_corrected')));
   if(item.scheduled)content.append(node('p',()=>tr('preference_scheduled')));
   if(item.validity_conflict)content.append(node('p',()=>tr('preference_validity_conflict')));
   if(item.category==='projects'&&window.openProjectTimeline){const timeline=node('button',()=>window.selfosI18n.t('timeline.open'),'pt-entry-button');timeline.type='button';timeline.dataset.projectTimeline='';timeline.onclick=()=>{el('kb-detail').close();window.openProjectTimeline(item.id);};content.append(timeline);}
   for(const field of ['decisions','blockers','next_steps'])if(item[field]?.length){const list=node('ul');item[field].forEach(value=>list.append(node('li',value)));content.append(node('h3',()=>tr(field)),list);}
   if(item.evidence)content.append(node('h3',()=>tr('quote')),node('pre',item.evidence));
   const notes={project_context:'project_context_note',session_context:'session_context_note',summary_context:'summary_context_note'};
   if(notes[item.source_scope])content.append(node('p',()=>tr(notes[item.source_scope])));
   content.append(node('h3',()=>tr('sources_heading')+' · '+window.selfosI18n.number(detailCache.source_count)));
   if(item.missing_source_count)content.append(node('p',()=>tr('missing_sources',{count:item.missing_source_count})));
   if(!detailCache.source_count&&!item.missing_source_count)content.append(node('p',()=>tr('empty_sources')));
   const holder=node('div');holder.id='kb-sources';const button=node('button',()=>tr('more_sources'),'kb-more');button.id='kb-more-sources';button.type='button';button.onclick=moreSources;content.append(holder,button);renderSources();
 }
 async function openDetail(id){
   activeId=id;detailCache=null;detailSources=[];sourceOffset=0;sourcePages=new Map();sourceListLoading=false;sourceListError='';const seq=++detailGeneration;
   el('kb-detail-content').replaceChildren(node('p',()=>tr('detail_loading')));el('kb-detail').showModal();
   try{const data=await request('/__knowledge_item__?'+new URLSearchParams({id}));if(seq!==detailGeneration)return;detailCache=data;detailSources=data.sources;sourceOffset=data.sources.length;renderDetail();}
   catch(error){if(seq===detailGeneration)el('kb-detail-content').replaceChildren(node('p',()=>errorText(error)));}
 }
 function translate(){
   for(const [id,key]of [['kb-heading','heading'],['kb-intro','intro'],['kb-project-label','project_label'],['kb-source-label','source_label'],['kb-date-from-label','date_from_label'],['kb-date-to-label','date_to_label'],['kb-reset','clear'],['kb-close','close']])bound(el(id),()=>tr(key));
   el('kb-search').placeholder=tr('search_placeholder');el('kb-search').setAttribute('aria-label',tr('search_label'));el('kb-detail').setAttribute('aria-label',tr('detail_label'));el('kb-tabs').setAttribute('aria-label',tr('all'));
   updateTabs();updateFilters();
 }
 window.browseKnowledge=key=>{if(categories.includes(key))category=key;clearTimeout(timer);load();el('knowledge-library').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});el('kb-heading').focus();};
 el('kb-search-form').addEventListener('submit',event=>{event.preventDefault();clearTimeout(timer);load();});
 el('kb-search').oninput=()=>{generation++;clearTimeout(timer);timer=setTimeout(()=>load(),250);};
 for(const id of ['kb-project','kb-source-filter','kb-date-from','kb-date-to'])el(id).onchange=()=>{clearTimeout(timer);load();};
 el('kb-reset').onclick=()=>{category='all';for(const id of ['kb-search','kb-project','kb-source-filter','kb-date-from','kb-date-to'])el(id).value='';clearTimeout(timer);load();el('kb-search').focus();};
 el('kb-more').onclick=()=>load(true);el('kb-retry').onclick=()=>load();el('kb-close').onclick=()=>el('kb-detail').close();
 el('kb-detail').addEventListener('close',()=>{detailGeneration++;activeId='';detailCache=null;});
 document.addEventListener('DOMContentLoaded',()=>{translate();load();});
})();
