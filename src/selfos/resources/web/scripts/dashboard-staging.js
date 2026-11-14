// Staging review
let _stagingFiles=[];
function checkStaging(){
 fetch('/__staging__').then(r=>r.json()).then(data=>{
  _stagingFiles=data.files||[];const button=document.getElementById('staging-btn');
  button.style.display=_stagingFiles.length?'':'none';
  window.selfosI18n.bindText(button,'ui.staging.pending',{count:_stagingFiles.length});
 }).catch(()=>{});
}
function openStagingModal(){
 const list=document.getElementById('staging-file-list');list.replaceChildren();
 _stagingFiles.forEach((file,index)=>{
  const item=document.createElement('div');item.className='staging-file-item selected';item.dataset.idx=index;
  const name=document.createElement('div');name.className='staging-file-name';name.textContent=file.name;
  const target=document.createElement('div');target.className='staging-file-target';
  window.selfosI18n.bindText(target,'ui.staging.target',()=>({target:file.target||window.selfosI18n.t('ui.staging.unknown_target')}));
  item.append(name,target);item.onclick=()=>item.classList.toggle('selected');list.appendChild(item);
 });
 document.getElementById('staging-modal').classList.add('open');
}
function closeStagingModal(){document.getElementById('staging-modal').classList.remove('open');}
function applySelectedStaging(){
 const items=document.querySelectorAll('.staging-file-item.selected');
 const filenames=Array.from(items).map(element=>_stagingFiles[+element.dataset.idx].name);
 if(!filenames.length){closeStagingModal();return;}
 const button=document.getElementById('staging-apply-btn');button.disabled=true;
 window.selfosI18n.bindText(button,'ui.staging.applying');
 fetch('/__staging__/apply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({files:filenames})})
 .then(async response=>{const data=await response.json();if(!response.ok||data.ok===false||(Array.isArray(data.errors)&&data.errors.length))throw Error('staging_failed');closeStagingModal();checkStaging();window.selfosI18n.bindText(button,'ui.staging.apply');})
 .catch(()=>window.selfosI18n.bindText(button,'ui.staging.failed'))
 .finally(()=>{button.disabled=false;});
}
document.getElementById('staging-modal').addEventListener('click',event=>{if(event.target===event.currentTarget)closeStagingModal();});
document.addEventListener('DOMContentLoaded',checkStaging);

