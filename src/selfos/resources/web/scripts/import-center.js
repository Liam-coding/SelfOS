(function(window,document){
 'use strict';
 window.selfosUI.register('import-center',()=>{
  let data=null,generation=0,timer=null,returnFocus=null,draftOpen=false;
  const requests=new Set(),cleanups=[];
  const el=id=>document.getElementById('import-center-'+id),t=(key,args)=>window.selfosI18n.t('center.'+key,args);
  function node(tag,text){const n=document.createElement(tag);n.textContent=text;return n;}
  function abort(){++generation;for(const c of requests)c.abort();requests.clear();if(timer!==null)clearTimeout(timer);timer=null;}
  function close(){abort();if(el('dialog').open)el('dialog').close();returnFocus?.focus();}
  function handoff(fn){close();fn();}
  function render(){
   if(!data)return;
   const sources=el('sources');sources.replaceChildren();
   for(const row of data.sources||[]){const a=node('article','');a.append(node('strong',row.path),node('small',t(row.diagnostics?.length?'missing':row.excluded?'excluded':row.available?'available':'missing')));
    a.append(node('small',t(row.kind==='opencode_database'?'native_source':'local_source')));
    a.append(node('small',row.scan?t('scanned',{date:row.scan.scanned_at,parts:row.scan.selected_parts}):t('unknown')));
    if(row.scan&&window.selfosI18n.has('native.'+row.scan.status))a.append(node('small',window.selfosI18n.t('native.'+row.scan.status)));
    if(row.scan?.diagnostics?.length)a.append(node('small',row.scan.diagnostics.join(', ')));sources.append(a);}
   if(!sources.childNodes.length)sources.append(node('p',t(data.diagnostics?.includes('source_metadata_unavailable')?'source_error':'empty')));
   const uploads=el('uploads');uploads.replaceChildren();
   for(const row of data.uploads?.items||[]){const a=node('article','');a.append(node('strong',row.original_filename),node('small',t(window.selfosI18n.has('center.'+row.status)?row.status:'original_or_index_unavailable')));
    if(row.uploaded_at)a.append(node('small',t('uploaded_time',{date:row.uploaded_at})));
    if(row.scan)a.append(node('small',t('scanned',{date:row.scan.scanned_at,parts:row.scan.selected_parts})));
    if(typeof row.indexed_parts==='number')a.append(node('small',t('coverage',{processed:row.processed_parts,indexed:row.indexed_parts})));uploads.append(a);}
   if(!uploads.childNodes.length)uploads.append(node('p',t('empty')));
   el('more').hidden=!data.uploads?.has_more;
   const job=data.job||{},running=!!job.running;
   el('job').textContent=running?t('running',{phase:job.phase,completed:job.completed,total:job.total}):t('idle');
   el('stop').disabled=!running||job.phase==='stopping';el('progress').disabled=!running;el('preview').disabled=running;
   const operations=el('operations');operations.replaceChildren();
   for(const op of (data.publication?.operations||[]).slice(0,20)){const a=node('article','');
    a.append(node('strong',op.id),node('small',t(op.published||op.was_published?'op_completed':op.status==='completed'?'op_provisional':window.selfosI18n.has('center.op_'+op.status)?'op_'+op.status:'op_unknown')));
    if(op.published||op.was_published){const b=node('button',t('changes'));b.type='button';b.dataset.centerOperation=op.id;if(!el('changes'))b.id='import-center-changes';a.append(b);}operations.append(a);}
   if(!operations.childNodes.length)operations.append(node('p',t('empty')));
   el('model').textContent=t('model',{provider:data.model?.provider||'',model:data.model?.model||t('default_model')});
   el('status').textContent=data.diagnostics?.length?t('diagnostic'):'';
  }
  async function refresh(more=false){
   if(!el('dialog').open)return;
   abort();const token=generation,c=new AbortController();requests.add(c);el('status').textContent=t('loading');
   const offset=more?(data?.uploads?.items.length||0):0;
   try{const response=await fetch('/__import_center__?offset='+offset+'&limit=50',{cache:'no-store',signal:c.signal});if(!response.ok)throw Error('unavailable');const next=await response.json();
    if(token!==generation||!el('dialog').open)return;
    if(more&&data)next.uploads.items=[...data.uploads.items,...next.uploads.items];data=next;render();
    if(next.job?.running)timer=setTimeout(()=>{timer=null;refresh();},1500);
   }catch(error){if(token===generation&&el('dialog').open)el('status').textContent=t('unavailable');}
   finally{requests.delete(c);}
  }
  function open(){returnFocus=document.activeElement;if(!el('dialog').open)el('dialog').showModal();render();refresh();}
  function action(event){
   const n=event.target.closest?.('[data-center-action],[data-center-operation]');if(!n||!n.closest('#import-center-dialog,#import-center-open'))return;
   if(n.dataset.centerOperation){handoff(()=>window.openKnowledgeChanges(n.dataset.centerOperation));return;}
   const actions={open,close,refresh:()=>refresh(),more:()=>refresh(true),sources:()=>handoff(()=>{const setup=window.selfosUI.module('onboarding');return setup.openSources?setup.openSources():setup.open();}),
    preview:()=>handoff(async()=>{const setup=window.selfosUI.module('onboarding');if(setup.openPreview)return setup.openPreview();await setup.open();await setup.preview('sample');}),
    uploads:()=>handoff(()=>window.selfosUploads.open()),progress:()=>handoff(()=>window.selfosUI.module('jobs').recover()),
    recovery:()=>handoff(()=>{const p=document.getElementById('import-publication');window.selfosUI.module('publication').openDetails();p?.scrollIntoView({behavior:'smooth',block:'center'});}),
    stop:async()=>{el('stop').disabled=true;const jobs=window.selfosUI.module('jobs');if(!jobs.snapshot().running)jobs.recover(data.job);await jobs.stop();refresh();}};
   if(Object.hasOwn(actions,n.dataset.centerAction)){event.preventDefault();actions[n.dataset.centerAction]();}
  }
  function on(n,type,f){n.addEventListener(type,f);cleanups.push(()=>n.removeEventListener(type,f));}
  function init(){on(document,'click',action);on(el('dialog'),'close',()=>{if(!el('dialog').open)abort();});on(document,'selfos-language',render);
   cleanups.push(window.selfosUI.module('jobs').subscribe(()=>{if(el('dialog').open)refresh();}));
   const overview=document.querySelector('.knowledge-overview');if(overview)overview.after(el('open'));
   if(draftOpen){draftOpen=false;open();}
  }
  function teardown(){draftOpen=el('dialog').open;abort();cleanups.splice(0).reverse().forEach(f=>f());}
  return {open,close,refresh,init,teardown,busy:()=>requests.size>0};
 },{dependencies:['jobs','onboarding','request','locale'],roots:['#import-center-dialog','#import-center-open']});
})(window,document);
