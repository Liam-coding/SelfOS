(function(window){
'use strict';
window.selfosUI.register('publication',()=>{
const requests=new Set(),cleanups=[];let lifetime=0,inflight=null,queued=false,detailsOpen=false;
function on(node,type,callback){node?.addEventListener?.(type,callback);cleanups.push(()=>node?.removeEventListener?.(type,callback));}

let importPublicationData = null;
let importOperationLimit = 10;
let importStatusGeneration = 0;
let importStatusFailed = false;
const importText=key=>window.selfosI18n.t(window.selfosI18n.has('import.'+key)?'import.'+key:'import.unknown');
const bindPublication=(element,text)=>window.selfosI18n.bindText(element,'ui.common.value',()=>({value:text()}));
const importCounts = counts => ['cards','lessons','personal_facts','preferences','history'].map(key => importText(key)+': '+window.selfosI18n.number(counts[key] || 0)).join(' · ');
function renderImportPublication(data) {
  importPublicationData = data;importStatusFailed=false;const owner=lifetime;
  const publication = data.publication || {operations:[]};
  bindPublication(document.getElementById('import-published'),()=>importText('title')+' — '+importCounts(data.counts || {}));
  bindPublication(document.getElementById('import-modal-published'),()=>document.getElementById('import-published').textContent);
  bindPublication(document.getElementById('import-modal-boundary'),()=>importText('saved')+': '+window.selfosI18n.number(data.saved_checkpoints || 0)+'. '+importText('boundary'));
  for(const [id,key] of [['import-details-title','details'],['import-boundary','boundary'],['import-provisional','provisional'],['import-validation','validation'],['import-refresh','retry'],['import-more','more']])window.selfosI18n.bindText(document.getElementById(id),'import.'+key);
  bindPublication(document.getElementById('import-checkpoints'),()=>importText('saved')+': '+window.selfosI18n.number(data.saved_checkpoints || 0));
  bindPublication(document.getElementById('import-diagnostic'),()=>importStatusFailed ? importText('error') : publication.diagnostics ? importText('diagnostics') : '');
  const container=document.getElementById('import-operations');container.replaceChildren();
  const operations=publication.operations || [];
  if(!operations.length){const p=document.createElement('p');bindPublication(p,()=>importText('empty'));container.append(p);}
  for(const operation of operations.slice(0,importOperationLimit)) {
    const row=document.createElement('article');row.style='border-top:1px solid var(--line,#ccc);padding:12px 0';
    const title=document.createElement('p');bindPublication(title,()=>operation.id+' · '+importText(operation.status)+' · '+importText(operation.phase));
    const compatibility=document.createElement('p');bindPublication(compatibility,()=>importText(operation.staged_snapshot_published ? 'installed' : operation.compatible===null ? 'unchecked' : operation.compatible ? 'compatible' : 'incompatible'));
    row.append(title,compatibility);
    if(operation.staged_counts){const counts=document.createElement('p');bindPublication(counts,()=>importText('staged')+' — '+importCounts(operation.staged_counts));row.append(counts);}
    if(operation.resume_eligible || operation.source_recheck_available){const button=document.createElement('button');button.type='button';bindPublication(button,()=>importText(operation.resume_eligible ? 'resume' : 'check_resume'));button.setAttribute('data-action','resume');button.addEventListener('click',()=>{if(owner!==lifetime)return;window.selfosUI.module('import-settings').close();window.selfosUI.module('jobs').start(false,true,false);});row.append(button);}
    else if(operation.policy_compatible===false && !operation.staged_snapshot_published && operation.status!=='running') {const button=document.createElement('button');button.type='button';bindPublication(button,()=>importText('rebuild'));button.addEventListener('click',()=>{if(owner!==lifetime)return;window.selfosUI.module('import-settings').close();window.selfosUI.module('jobs').start(false,true,true);});row.append(button);}
    container.append(row);
  }
  document.getElementById('import-more').hidden=operations.length<=importOperationLimit;
}

function refreshImportPublication(force=false){
  if(inflight){if(force)queued=true;return inflight;}
  const generation=++importStatusGeneration,controller=new AbortController();requests.add(controller);
  inflight=(async()=>{
    try{const response=await fetch('/__knowledge_settings__',{cache:'no-store',signal:controller.signal});if(!response.ok)throw Error('status');const data=await response.json();if(generation===importStatusGeneration)renderImportPublication(data);}
    catch(error){if(generation===importStatusGeneration){importStatusFailed=true;bindPublication(document.getElementById('import-diagnostic'),()=>importText('error'));if(!importPublicationData)bindPublication(document.getElementById('import-published'),()=>importText('error'));}}
    finally{requests.delete(controller);if(generation===importStatusGeneration){inflight=null;if(queued){queued=false;refreshImportPublication();}}}
  })();return inflight;
}
function init(){
  ++lifetime;
  const header=document.querySelector('.header');if(header)header.insertAdjacentElement('afterend',document.getElementById('import-publication'));
  on(document.getElementById('import-refresh'),'click',()=>refreshImportPublication());
  on(document.getElementById('import-more'),'click',()=>{importOperationLimit+=10;if(importPublicationData)renderImportPublication(importPublicationData);});
  cleanups.push(window.selfosUI.module('jobs').subscribe(state=>{if(state.kind==='knowledge'&&state.event==='finished')refreshImportPublication(true);}));
  if(importPublicationData)renderImportPublication(importPublicationData);
  if(detailsOpen)document.querySelector('#import-publication details').open=true;
  refreshImportPublication();
}
function teardown(){
  detailsOpen=!!document.querySelector('#import-publication details')?.open;++lifetime;++importStatusGeneration;
  for(const controller of requests)controller.abort();requests.clear();inflight=null;queued=false;cleanups.splice(0).reverse().forEach(cleanup=>cleanup());
}
return {openDetails(){detailsOpen=true;document.querySelector('#import-publication details').open=true;},render:renderImportPublication,refresh:refreshImportPublication,busy:()=>requests.size>0,init,teardown};
},{dependencies:['jobs','request','locale'],roots:['#import-publication']});
for(const [name,method]of Object.entries({renderImportPublication:'render',refreshImportPublication:'refresh'}))if(!window[name])window[name]=(...args)=>window.selfosUI.module('publication')[method](...args);
})(window);
