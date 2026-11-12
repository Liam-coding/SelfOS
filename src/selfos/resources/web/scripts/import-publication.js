
let importPublicationData = null;
let importOperationLimit = 10;
let importStatusGeneration = 0;
let importStatusFailed = false;
const importText = key => (importLocales[document.documentElement.lang === 'zh' ? 'zh' : 'en'][key] || importLocales.en.unknown);
const importCounts = counts => ['cards','lessons','personal_facts','preferences','history'].map(key => importText(key)+': '+(counts[key] || 0)).join(' · ');
function renderImportPublication(data) {
  importPublicationData = data;
  const publication = data.publication || {operations:[]};
  document.getElementById('import-published').textContent=importText('title')+' — '+importCounts(data.counts || {});
  document.getElementById('import-modal-published').textContent=document.getElementById('import-published').textContent;
  document.getElementById('import-modal-boundary').textContent=importText('saved')+': '+(data.saved_checkpoints || 0)+'. '+importText('boundary');
  for(const [id,key] of [['import-details-title','details'],['import-boundary','boundary'],['import-provisional','provisional'],['import-validation','validation'],['import-refresh','retry'],['import-more','more']])document.getElementById(id).textContent=importText(key);
  document.getElementById('import-checkpoints').textContent=importText('saved')+': '+(data.saved_checkpoints || 0);
  document.getElementById('import-diagnostic').textContent=importStatusFailed ? importText('error') : publication.diagnostics ? importText('diagnostics') : '';
  const container=document.getElementById('import-operations');container.replaceChildren();
  const operations=publication.operations || [];
  if(!operations.length){const p=document.createElement('p');p.textContent=importText('empty');container.append(p);}
  for(const operation of operations.slice(0,importOperationLimit)) {
    const row=document.createElement('article');row.style='border-top:1px solid var(--line,#ccc);padding:12px 0';
    const title=document.createElement('p');title.textContent=operation.id+' · '+importText(operation.status)+' · '+importText(operation.phase);
    const compatibility=document.createElement('p');compatibility.textContent=importText(operation.staged_snapshot_published ? 'installed' : operation.compatible===null ? 'unchecked' : operation.compatible ? 'compatible' : 'incompatible');
    row.append(title,compatibility);
    if(operation.staged_counts){const counts=document.createElement('p');counts.textContent=importText('staged')+' — '+importCounts(operation.staged_counts);row.append(counts);}
    if(operation.resume_eligible || operation.source_recheck_available){const button=document.createElement('button');button.type='button';button.textContent=importText(operation.resume_eligible ? 'resume' : 'check_resume');button.setAttribute('data-action','resume');button.onclick=()=>{document.getElementById('knowledge-settings').close?.();confirmHarvest(false,true,false);};row.append(button);}
    else if(operation.policy_compatible===false && !operation.staged_snapshot_published && operation.status!=='running') {const button=document.createElement('button');button.type='button';button.textContent=importText('rebuild');button.onclick=()=>{document.getElementById('knowledge-settings').close?.();confirmHarvest(false,true,true);};row.append(button);}
    container.append(row);
  }
  document.getElementById('import-more').hidden=operations.length<=importOperationLimit;
}
async function refreshImportPublication() {
  const generation=++importStatusGeneration;
  try {
    const response=await fetch('/__knowledge_settings__',{cache:'no-store'});
    if(!response.ok)throw new Error('status');
    const data=await response.json();if(generation===importStatusGeneration){importStatusFailed=false;renderImportPublication(data);}
  }catch(error){if(generation===importStatusGeneration){importStatusFailed=true;document.getElementById('import-diagnostic').textContent=importText('error');if(!importPublicationData)document.getElementById('import-published').textContent=importText('error');}}
}
document.addEventListener('DOMContentLoaded',()=>{
 const header=document.querySelector?.('.header');
 if(header)header.insertAdjacentElement('afterend',document.getElementById('import-publication'));
 document.getElementById('import-refresh').onclick=refreshImportPublication;
 document.getElementById('import-more').onclick=()=>{importOperationLimit+=10;if(importPublicationData)renderImportPublication(importPublicationData);};
 refreshImportPublication();
});
document.addEventListener('selfos-language',()=>{if(importPublicationData)renderImportPublication(importPublicationData);else if(importStatusFailed)document.getElementById('import-published').textContent=importText('error');});
document.addEventListener('selfos-import-finished',refreshImportPublication);
