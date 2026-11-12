"""Publication status component with packaged locale strings."""
import json
from importlib.resources import files

LOCALES = {language: json.loads(files('selfos.resources').joinpath(
    'locales', folder, 'import.json').read_text(encoding='utf-8'))
    for language, folder in [('en', 'en'), ('zh', 'zh-CN')]}

HTML = '''<style>
#import-publication{width:calc(100% - 48px);max-width:1200px;margin:20px auto;padding:20px;box-sizing:border-box;font-size:13px;line-height:1.6;overflow-wrap:anywhere;border:1px solid var(--line,#dce3ee);border-radius:20px;background:var(--surface,#fff);color:var(--text,#22304a)}
#import-publication p{margin:10px 0}#import-publication summary{cursor:pointer;font-weight:600;color:var(--blue,#2474db)}
#import-publication button{border:1px solid var(--line,#cdd7e5);border-radius:10px;padding:9px 13px;margin:4px 6px 4px 0;background:var(--surface,#fff);color:var(--text,#22304a);font:inherit;cursor:pointer}
#import-publication button:hover{border-color:var(--blue,#2474db)}
</style><section id="import-publication" aria-label="Knowledge publication">
<p id="import-published" role="status">Loading publication status…</p>
<details><summary id="import-details-title">Import progress and saved work</summary>
<p id="import-boundary"></p><p id="import-checkpoints"></p>
<p id="import-provisional"></p><p id="import-validation"></p>
<p id="import-diagnostic" role="status"></p>
<div id="import-operations"></div>
<button id="import-more" type="button" hidden></button>
<button id="import-refresh" type="button">Refresh status</button>
</details></section>'''

SCRIPT = 'const importLocales = ' + json.dumps(LOCALES, ensure_ascii=True) + ';\n' + r'''
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
'''
