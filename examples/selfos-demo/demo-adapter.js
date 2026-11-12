/* Read-only fictional fixture adapter: requests never reach a server or model. */
(() => {
 const data=__DEMO_DATA__;
 try{localStorage.setItem('selfos-lang','__DEMO_LOCALE__');localStorage.setItem('selfos-theme','light');}catch(e){}
 const answer=(value,status=200)=>Promise.resolve(new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}}));
 window.fetch=(input,options={})=>{
  const url=new URL(typeof input==='string'?input:input.url,'https://demo.selfos.local');
  if((options.method||input?.method||'GET').toUpperCase()!=='GET')return answer({code:'demo_read_only'},405);
  const query=url.searchParams,offset=Number(query.get('offset')||0),limit=Number(query.get('limit')||20);
  if(url.pathname==='/__knowledge__'){
   const category=query.get('category')||'all',search=(query.get('query')||'').toLowerCase().trim();
   let items=data.listing.items.filter(row=>!search||[row.title,row.summary,data.details[row.id].item.evidence].join(' ').toLowerCase().includes(search));
   if(query.get('project'))items=items.filter(row=>row.project_contexts.some(p=>p.id===query.get('project')));
   if(query.get('source'))items=items.filter(row=>row.source_types.includes(query.get('source')));
   if(query.get('date_from'))items=items.filter(row=>row.date.slice(0,10)>=query.get('date_from'));
   if(query.get('date_to'))items=items.filter(row=>row.date.slice(0,10)<=query.get('date_to'));
   const counts={projects:0,lessons:0,personal_facts:0,preferences:0,history:0};
   items.forEach(row=>counts[row.category]++);
   items=items.filter(row=>category==='all'||row.category===category);
   return answer({...data.listing,items:items.slice(offset,offset+limit),total:items.length,filtered_counts:counts});
  }
  if(url.pathname==='/__knowledge_item__'){
   const detail=data.details[query.get('id')];
   if(!detail)return answer({code:'not_found'},404);
   return answer({...detail,sources:detail.sources.slice(offset,offset+limit),source_offset:offset});
  }
  if(url.pathname==='/__knowledge_source__'){
   const text=data.texts[query.get('id')];
   if(text===undefined)return answer({code:'source_missing'},404);
   const chars=Array.from(text),end=offset+limit;
   return answer({text:chars.slice(offset,end).join(''),text_total:chars.length,next_offset:end<chars.length?end:null});
  }
  if(url.pathname==='/__knowledge_timeline__'){
   const timeline=data.timelines[query.get('id')];
   if(!timeline)return answer({code:'not_found'},404);
   const category=query.get('category')||'all';
   const items=timeline.items.filter(row=>category==='all'||row.type===category);
   return answer({...timeline,items:items.slice(offset,offset+limit),total:items.length,offset,limit});
  }
  if(url.pathname==='/__knowledge_settings__')return answer({settings:{domains:['work','learning','health','life','personal'],detail:'balanced'},counts:data.counts,saved_checkpoints:0,publication:{operations:[],diagnostics:0}});
  if(url.pathname==='/__model_settings__')return answer({provider:'anthropic',model:'',proxy_mode:'direct',proxy_source:'direct',effective_proxy:{},has_api_key:false});
  if(url.pathname==='/__staging__')return answer({sessions:[],items:[]});
  if(url.pathname==='/__knowledge_run__')return answer({running:false,result:null});
  return answer({code:'demo_read_only'},405);
 };
 window.EventSource=class{constructor(){throw Error('This fixture does not start imports or model requests.');}};
 document.addEventListener('DOMContentLoaded',()=>{
  for(const button of document.querySelectorAll('[onclick*="confirmHarvest"],[onclick*="confirmKnowledge"],[onclick*="openHarvestModal"]')){button.disabled=true;button.title='Read-only demonstration';}
 });
})();
