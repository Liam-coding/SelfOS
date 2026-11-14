(function(window){'use strict';window.selfosUI.register('staging',()=>{
let _stagingFiles=[],generation=0,applying=false,inflight=null,queued=false,unsubscribe=null;
const requests=new Set();let draft=null;
function request(url,options={}){const controller=new AbortController();requests.add(controller);return fetch(url,{...options,signal:controller.signal}).finally(()=>requests.delete(controller));}
function checkStaging(){
 if(inflight){queued=true;return inflight;}const owner=generation;
 inflight=request('/__staging__',{cache:'no-store'}).then(response=>{if(!response.ok)throw Error('staging');return response.json();}).then(data=>{
  if(owner!==generation)return;_stagingFiles=data.files||[];const button=document.getElementById('staging-btn');
  button.style.display=_stagingFiles.length?'':'none';window.selfosI18n.bindText(button,'ui.staging.pending',{count:_stagingFiles.length});
 }).catch(()=>{}).finally(()=>{if(owner===generation){inflight=null;if(queued){queued=false;checkStaging();}}});return inflight;
}
function openStagingModal(){
 const owner=generation;const list=document.getElementById('staging-file-list');list.replaceChildren();
 _stagingFiles.forEach((file,index)=>{
  const item=document.createElement('div');item.className='staging-file-item selected';item.dataset.filename=file.name;
  const name=document.createElement('div');name.className='staging-file-name';name.textContent=file.name;
  const target=document.createElement('div');target.className='staging-file-target';
  window.selfosI18n.bindText(target,'ui.staging.target',()=>({target:file.target||window.selfosI18n.t('ui.staging.unknown_target')}));
  item.append(name,target);item.addEventListener('click',()=>{if(owner===generation)item.classList.toggle('selected');});list.appendChild(item);
 });
 document.getElementById('staging-modal').classList.add('open');
}
function closeStagingModal(){document.getElementById('staging-modal').classList.remove('open');}
function applySelectedStaging(){
 if(applying||window.selfosReadOnlyDemo)return;const owner=generation;applying=true;
 const items=document.querySelectorAll('.staging-file-item.selected');
 const filenames=Array.from(items).map(element=>element.dataset.filename);
 if(!filenames.length){applying=false;closeStagingModal();return;}
 const button=document.getElementById('staging-apply-btn');button.disabled=true;
 window.selfosI18n.bindText(button,'ui.staging.applying');
 request('/__staging__/apply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({files:filenames})})
 .then(async response=>{const data=await response.json();if(!response.ok||data.ok===false||(Array.isArray(data.errors)&&data.errors.length))throw Error('staging_failed');if(owner!==generation)return;closeStagingModal();checkStaging();window.selfosI18n.bindText(button,'ui.staging.apply');})
 .catch(()=>{if(owner===generation)window.selfosI18n.bindText(button,'ui.staging.failed');})
 .finally(()=>{if(owner===generation){applying=false;button.disabled=false;}});
}

function backdrop(event){if(event.target===event.currentTarget)closeStagingModal();}
function action(event){const node=event.target.closest?.('[data-selfos-action]');if(!node||!document.contains(node)||!node.closest('#staging-modal,#staging-btn'))return;const actions={'staging.open':openStagingModal,'staging.close':closeStagingModal,'staging.apply':applySelectedStaging};if(!Object.hasOwn(actions,node.dataset.selfosAction))return;event.preventDefault();actions[node.dataset.selfosAction]();}
function init(){++generation;document.addEventListener('click',action);document.getElementById('staging-modal').addEventListener('click',backdrop);unsubscribe=window.selfosUI.module('jobs').subscribe(state=>{if(state.event==='finished')checkStaging();});if(draft){_stagingFiles=draft.files;if(draft.open){openStagingModal();for(const row of document.querySelectorAll('.staging-file-item'))if(!draft.selected.includes(row.dataset.filename))row.classList.remove('selected');}draft=null;}checkStaging();}
function teardown(){draft={files:_stagingFiles,open:document.getElementById('staging-modal').classList.contains('open'),selected:[...document.querySelectorAll('.staging-file-item.selected')].map(row=>row.dataset.filename)};++generation;for(const controller of requests)controller.abort();requests.clear();inflight=null;queued=false;applying=false;document.getElementById('staging-apply-btn').disabled=false;unsubscribe?.();unsubscribe=null;document.removeEventListener('click',action);document.getElementById('staging-modal').removeEventListener('click',backdrop);}
return {refresh:checkStaging,open:openStagingModal,close:closeStagingModal,apply:applySelectedStaging,init,teardown,busy:()=>requests.size>0};
},{dependencies:['jobs','request','locale'],roots:['#staging-modal','#staging-btn']});
for(const [name,method]of Object.entries({checkStaging:'refresh',openStagingModal:'open',closeStagingModal:'close',applySelectedStaging:'apply'}))if(!window[name])window[name]=(...args)=>window.selfosUI.module('staging')[method](...args);
})(window);
