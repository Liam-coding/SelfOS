(() => {
 const el=id=>document.getElementById(id);
 const tr=(key,values={})=>window.selfosI18n.t('changes.'+key,values);
 const text=(tag,value)=>{const node=document.createElement(tag);window.selfosI18n.bindText(node,'ui.common.value',()=>({value:typeof value==='function'?value():value}));return node;};
 const button=(value,handler)=>{const node=text('button',value);node.type='button';node.addEventListener('click',handler);return node;};
 let generation=0,detailGeneration=0,sourceGeneration=0,listCursor=null,listProof=null,detailCursor=null,event=null,source=null,recordTarget=null,recordCursor=null;
 async function request(path,query){const response=await fetch(path+'?'+new URLSearchParams(query));const data=await response.json();if(!response.ok)throw new Error(data.status||'history_unavailable');return data;}
 function status(key,target='changes-status'){el(target).replaceChildren(text('span',()=>tr(key)));}
 function clearSource(){sourceGeneration++;source=null;el('changes-source-text').replaceChildren();el('changes-source-text').hidden=true;el('changes-source-more').hidden=true;el('changes-source-status').replaceChildren();}
 async function list(more=false){
   const current=++generation;detailGeneration++;clearSource();el('changes-more').hidden=true;status('loading');
   if(!more){listCursor=null;listProof=null;event=null;el('changes-operations').replaceChildren();el('changes-before-after').replaceChildren(text('p',()=>tr('select')));el('changes-detail-more').hidden=true;}
   try{const data=await request('/__knowledge_changes__',{category:el('changes-category').value,action:el('changes-action').value,conflict:String(el('changes-conflicts').checked),...(listCursor?{cursor:listCursor}:{})});
     if(current!==generation)return;if(data.status!=='verified'){status(data.status);return;}listCursor=data.cursor;listProof=data.cursor;
     for(const item of data.items){const entry=document.createElement('button');entry.type='button';entry.append(text('span',()=>tr(item.kind)+' · '+tr(item.state)+' · '+window.selfosI18n.date(item.recorded_at,{timeStyle:'short'})));entry.addEventListener('click',()=>detail(item.id,false,entry));entry.className='changes-operation';entry.dataset.event=item.id;entry.setAttribute('aria-pressed','false');
       entry.append(text('p',()=>Object.entries(item.counts).map(([key,value])=>tr(key)+': '+window.selfosI18n.number(value)).join(' · ')));if(item.conflict_count)entry.append(text('p',()=>tr('conflict')+': '+item.conflict_count));el('changes-operations').append(entry);}
     el('changes-more').hidden=!data.has_more;status(data.boundary?'not_included':el('changes-operations').childElementCount?'verified':'empty');
   }catch(error){if(current===generation)status(error.message);}
 }
 function snapshots(items,label,eventId,proof){const box=document.createElement('div');box.append(text('h4',()=>tr(label)));if(!items.length)box.append(text('p',()=>tr('no_value')));
   for(const snapshot of items){const record=snapshot.record;for(const value of [record.title,record.value,record.text,record.intent].filter(Boolean))box.append(text('p',value));
     if(record.scope)box.append(text('p',()=>tr('scope')+': '+record.scope));if(record.valid_from)box.append(text('p',()=>tr('effective')+': '+record.valid_from));
     if(record.valid_until)box.append(text('p',()=>tr('valid_until')+': '+record.valid_until));
     if(record.status)box.append(text('p',()=>tr('status')+': '+(window.selfosI18n.has('search.status_'+record.status)?window.selfosI18n.t('search.status_'+record.status):record.status)));
     for(const key of ['decisions','blockers','next_steps'])if(record[key]?.length){box.append(text('h4',()=>window.selfosI18n.t('search.'+key)));for(const value of record[key])box.append(text('p',value));}
     for(const id of snapshot.source_ids)box.append(button(()=>tr('source')+' · '+id.slice(0,12),()=>viewSource(eventId,id,proof)));}
   return box;
 }
 async function detail(id,more=false,entry=null){
   const current=++detailGeneration;clearSource();event=id;status('loading');el('changes-detail-more').hidden=true;
   if(!more){detailCursor=listProof;el('changes-before-after').replaceChildren();for(const node of el('changes-operations').children)node.setAttribute('aria-pressed',String(node===entry));}
   try{const data=await request('/__knowledge_change__',{id,...(detailCursor?{cursor:detailCursor}:{})});if(current!==detailGeneration)return;detailCursor=data.cursor||detailCursor;
     if(data.status!=='verified'){status(data.status);el('changes-detail-more').hidden=!data.has_more;return;}
     if(data.reverted_receipts?.length&&!more){el('changes-before-after').append(text('h3',()=>tr('reverted_targets')));for(const target of data.reverted_receipts)el('changes-before-after').append(button(target,()=>{listProof=data.cursor;detail(target);}));}
     for(const change of data.items){const box=document.createElement('article');box.className='changes-change';box.append(text('h3',()=>window.selfosI18n.t('search.'+change.category)+' · '+tr(change.action)));if(change.conflict)box.append(text('p',()=>tr('conflict')));
       box.append(text('p',()=>window.selfosI18n.has('changes.'+change.reason)?tr(change.reason):tr('reason')+': '+change.reason));const values=document.createElement('div');values.className='changes-values';values.append(snapshots(change.before,'before',id,data.cursor),snapshots(change.after,'after',id,data.cursor));box.append(values);
       box.append(button(()=>tr('current'),()=>{el('knowledge-changes').close();window.browseKnowledge(change.category);}));el('changes-before-after').append(box);}
     status(data.state);el('changes-detail-more').hidden=!data.has_more;
   }catch(error){if(current===detailGeneration)status(error.message);}
 }
 async function viewSource(eventId,id,proof,more=false){
   if(!more)clearSource();const current=++sourceGeneration;status('loading','changes-source-status');el('changes-source-more').hidden=true;
   const offset=more&&source?source.offset:0;
   try{const data=await request('/__knowledge_change_source__',{id:eventId,source:id,cursor:proof,offset});if(current!==sourceGeneration)return;
     if(data.status!=='verified'){status(data.status,'changes-source-status');source={eventId,id,proof:data.cursor||proof,offset};el('changes-source-more').hidden=data.status!=='verification_pending';return;}
     if(!more)el('changes-source-text').replaceChildren();el('changes-source-text').append(document.createTextNode(data.text));el('changes-source-text').hidden=false;status('verified','changes-source-status');
     source={eventId,id,proof,offset:data.next_offset};el('changes-source-more').hidden=data.next_offset===null;
   }catch(error){if(current===sourceGeneration)status(window.selfosI18n.has('changes.'+error.message)?error.message:'source_missing','changes-source-status');}
 }
 el('knowledge-changes-entry').addEventListener('click',()=>{el('knowledge-changes').showModal();list();});
 el('changes-close').addEventListener('click',()=>el('knowledge-changes').close());el('knowledge-changes').addEventListener('close',()=>{generation++;detailGeneration++;clearSource();});
 for(const id of ['changes-category','changes-action','changes-conflicts'])el(id).addEventListener('change',()=>list());
 el('changes-restart').addEventListener('click',()=>{recordTarget=null;list();});el('changes-more').addEventListener('click',()=>list(true));el('changes-detail-more').addEventListener('click',()=>recordTarget?findRecord(true):detail(event,true));
 el('changes-source-more').addEventListener('click',()=>{if(source)viewSource(source.eventId,source.id,source.proof,true);});
 async function findRecord(more=false){
   const current=++detailGeneration;status('loading');if(!more)recordCursor=null;
   try{const data=await request('/__knowledge_record_changes__',{record:recordTarget,...(recordCursor?{cursor:recordCursor}:{})});if(current!==detailGeneration)return;recordCursor=data.cursor;
     if(data.status==='verified'){recordTarget=null;listProof=data.cursor;detail(data.id);}else{status(data.status);el('changes-detail-more').hidden=!data.has_more;}
   }catch(error){if(current===detailGeneration)status(error.message);}
 }
 window.openKnowledgeChanges=(id,category='all',record=null)=>{el('changes-category').value=category;el('knowledge-changes').showModal();list().then(()=>{recordTarget=record;if(record)findRecord();else if(id)detail(id);});};
})();
