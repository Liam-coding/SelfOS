(function(window){'use strict';window.selfosUI.register('quality',()=>{
 const el=id=>document.getElementById(id);
 const tr=(key,values={})=>window.selfosI18n.t('quality.'+key,values);
 const node=(tag,content)=>{const n=document.createElement(tag);window.selfosI18n.bindText(n,'ui.common.value',()=>({value:content()}));return n;};
 const category=key=>window.selfosI18n.t('search.'+key);
 let generation=0, fetching=false, queued=false;const requests=new Set();let unsubscribe=null;
 function render(data){
   el('quality-content').replaceChildren();
   const content=el('quality-content');
   content.append(node('p',()=>tr('limits')));
   if(data.incomplete)content.append(node('p',()=>tr('incomplete')));
   if(data.scoped)content.append(node('p',()=>tr('scoped')));
   const counts=document.createElement('article');counts.append(node('h3',()=>tr('current')));
   for(const [key,value] of Object.entries(data.counts))counts.append(node('p',()=>category(key==='cards'?'projects':key)+': '+window.selfosI18n.number(value)));
   content.append(counts);
   for(const [key,item] of Object.entries(data.categories)){
     const box=document.createElement('article');box.append(node('h3',()=>category(key)),node('p',()=>tr(item.explanation)),
       node('p',()=>tr('coverage',{count:item.reviewed_session_parts})));content.append(box);
   }
   const stages=document.createElement('article');stages.append(node('h3',()=>tr('stages')));
   for(const [key,item] of Object.entries(data.stages)){
     stages.append(node('p',()=>tr(key)+': '+window.selfosI18n.number(item.total)+' '+tr(item.unit)));
     if(key==='filtering')stages.append(node('p',()=>item.input_messages===undefined?tr('filtering_unknown'):tr('filtering_input',{count:item.input_messages})));
   }content.append(stages);
   const examples=document.createElement('article');examples.append(node('h3',()=>tr('examples')));
   if(!data.examples.length)examples.append(node('p',()=>tr('unknown')));
   for(const item of data.examples){
     const box=document.createElement('div');box.append(node('p',()=>tr(item.stage)+' · '+(item.category==='all'?tr('all'):category(item.category))+' · '+tr(item.reason)));
     if(item.record_id){const button=node('button',()=>tr('record'));button.type='button';button.onclick=()=>window.openKnowledgeDetail(item.record_id);box.append(button);}
     if(item.job_id){const job=node('a',()=>tr('jobs')+' '+item.job_id);job.href='#import-publication';box.append(job);}
     for(const identity of item.source_ids){
       if(item.source_available===false){box.append(node('p',()=>tr('source_unavailable')+' '+identity.slice(0,12)));continue;}
       const link=node('a',()=>tr('source')+' '+identity.slice(0,12));link.href='/__knowledge_source__?id='+encodeURIComponent(identity);link.target='_blank';link.rel='noopener noreferrer';box.append(link);
     }
     examples.append(box);
   }content.append(examples);
   const jobs=document.createElement('article');jobs.append(node('h3',()=>tr('jobs')),node('p',()=>tr('staging')));
   for(const item of data.jobs){
     const link=node('a',()=>item.id+' · '+window.selfosI18n.t('import.'+item.status)+(item.retryable?' · '+tr('retryable'):''));
     link.href='#import-publication';link.onclick=()=>{const details=document.querySelector('#import-publication details');if(details)details.open=true;};jobs.append(link);
   }content.append(jobs);
 }
 async function refresh(){
   if(fetching){queued=true;return;}fetching=true;
   const current=generation,controller=new AbortController();requests.add(controller);
   el('quality-status').replaceChildren(node('span',()=>tr('loading')));
   try{const response=await fetch('/__knowledge_quality__',{cache:'no-store',signal:controller.signal});if(!response.ok)throw Error('quality');const data=await response.json();if(current!==generation)return;render(data);el('quality-status').replaceChildren();}
   catch(error){if(current===generation){el('quality-content').replaceChildren();el('quality-status').replaceChildren(node('span',()=>tr('error')));}}
   finally{requests.delete(controller);if(current===generation){fetching=false;if(queued){queued=false;refresh();}}}
 }
 function init(){++generation;el('quality-refresh').addEventListener('click',refresh);unsubscribe=window.selfosUI.module('jobs').subscribe(state=>{if(state.kind==='knowledge'&&state.event==='finished')refresh();});refresh();}
 function teardown(){++generation;for(const controller of requests)controller.abort();requests.clear();fetching=false;queued=false;unsubscribe?.();unsubscribe=null;el('quality-refresh').removeEventListener('click',refresh);}
 return {refresh,render,init,teardown,busy:()=>requests.size>0};
},{dependencies:['jobs','request','locale'],roots:['#knowledge-quality']});})(window);
