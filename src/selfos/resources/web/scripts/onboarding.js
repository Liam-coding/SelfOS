let onboardingData=null,onboardingGeneration=0,onboardingBusy=false,onboardingSourcesDirty=false,onboardingReturnFromModel=false;
const onboardingElement=id=>document.getElementById('onboarding-'+id);
const onboardingText=(id,key,params={})=>window.selfosI18n.bindText(onboardingElement(id),'onboarding.'+key,params);
async function onboardingRequest(body){
  const response=await fetch('/__onboarding__',body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await response.json();if(!response.ok){const error=new Error(data.code||'onboarding_unavailable');error.code=data.code;throw error;}return data;
}
function renderOnboarding(){
  if(!onboardingData)return;
  const data=onboardingData,step=data.progress.step;
  document.querySelectorAll('[data-onboarding-step]').forEach(section=>section.hidden=Number(section.dataset.onboardingStep)!==step);
  onboardingText('step-label','step',{step:step+1});
  onboardingElement('back').disabled=onboardingBusy||step===0;
  onboardingElement('next').hidden=step>=3;onboardingElement('next').disabled=onboardingBusy;
  for(const id of ['save-sources','preview','more','skip','new-allowance'])onboardingElement(id).disabled=onboardingBusy;
  const availability=onboardingElement('availability');availability.replaceChildren();
  for(const source of data.availability){const p=document.createElement('p');p.textContent=source.path+' · '+window.selfosI18n.t('onboarding.'+(source.available?'available':'missing'));availability.append(p);}
  if(!onboardingSourcesDirty){onboardingElement('roots').value=data.sources.roots.join('\n');onboardingElement('exclusions').value=data.sources.exclusions.join('\n');}
  onboardingText('model-status','current_model',{provider:data.model.provider,model:data.model.model||window.selfosI18n.t('onboarding.not_configured')});
  const preview=data.preview,budget=data.budget;
  onboardingElement('excerpts').replaceChildren();
  const warningList=document.createElement('div');
  if(preview)for(const warning of preview.warnings){const p=document.createElement('p');const key='onboarding.warning_'+warning.code;p.textContent=window.selfosI18n.t(window.selfosI18n.has(key)?key:'onboarding.clipped')+(warning.path?' · '+warning.path:'');warningList.append(p);}
  if(preview){
    onboardingText('preview-summary','preview_counts',{files:preview.files.length,parts:preview.sessions.length,messages:preview.message_ids.length,remaining:budget.remaining,limit:budget.limit});
    onboardingText('preview-warning',preview.clipped?'clipped':'complete_preview');
    for(const session of preview.sessions){const article=document.createElement('article');const title=document.createElement('strong');title.textContent=session.project_id;article.append(title);
      for(const message of session.messages){const pre=document.createElement('pre');pre.textContent=message.role+' · '+message.timestamp+'\n'+message.path+'\n'+message.text;article.append(pre);}onboardingElement('excerpts').append(article);}
    onboardingElement('excerpts').prepend(warningList);
  }else{onboardingText('preview-summary','no_preview');onboardingElement('preview-warning').textContent='';}
  const canStart=Boolean(preview&&preview.sessions.length&&budget.remaining>0);
  onboardingElement('start').disabled=onboardingBusy||!canStart;onboardingElement('resume-sample').disabled=onboardingBusy||!canStart;
  onboardingElement('new-allowance').hidden=!preview||budget.remaining>0;
  const counts=data.knowledge.counts;
  onboardingText('result-status','result_counts',{projects:counts.cards,facts:counts.personal_facts,preferences:counts.preferences,lessons:counts.lessons,saved:data.knowledge.saved_checkpoints});
  onboardingElement('welcome').hidden=data.progress.status==='skipped'||Object.values(counts).some(value=>value>0);
}
async function openOnboarding(){
  const dialog=onboardingElement('dialog'),generation=++onboardingGeneration;
  if(!dialog.open)dialog.showModal();onboardingBusy=true;renderOnboarding();onboardingText('status','loading');
  try{const data=await onboardingRequest();if(generation!==onboardingGeneration||!dialog.open)return;onboardingData=data;onboardingText('status','ready');}
  catch(error){if(generation===onboardingGeneration)onboardingText('status','unavailable');}
  finally{if(generation===onboardingGeneration){onboardingBusy=false;renderOnboarding();}}
}
window.openOnboarding=openOnboarding;
async function onboardingPerform(body){
  if(onboardingBusy)return null;const generation=++onboardingGeneration;onboardingBusy=true;renderOnboarding();onboardingText('status','loading');
  try{const data=await onboardingRequest(body);if(generation===onboardingGeneration){onboardingData=data;if(body.action==='save_sources')onboardingSourcesDirty=false;renderOnboarding();onboardingText('status','ready');}return data;}
  catch(error){if(generation===onboardingGeneration)onboardingText('status',error.code==='onboarding_import_active'?'import_active':'invalid');return null;}
  finally{if(generation===onboardingGeneration){onboardingBusy=false;renderOnboarding();}}
}
async function onboardingStep(direction){if(!onboardingData)return;const step=onboardingData.progress.step;if(direction>0&&step===1&&onboardingSourcesDirty){if(!await onboardingSaveSources())return;}await onboardingPerform({action:'save_step',step:Math.max(0,Math.min(4,step+direction))});}
async function onboardingSaveSources(){const lines=id=>onboardingElement(id).value.split(/\r?\n/).map(line=>line.trim()).filter(Boolean);return await onboardingPerform({action:'save_sources',sources:{roots:lines('roots'),exclusions:lines('exclusions')}});}
async function onboardingPreview(tier){await onboardingPerform({action:'preview',tier});}
async function onboardingNewAllowance(){if(onboardingData?.preview)await onboardingPerform({action:'new_allowance',preview_id:onboardingData.preview.id});}
async function onboardingStart(){if(!onboardingData?.preview)return;const data=await onboardingPerform({action:'start',preview_id:onboardingData.preview.id});if(data?.stream_url){onboardingElement('dialog').close();confirmHarvest(false,true,false,data.stream_url);}}
async function onboardingSkip(){if(await onboardingPerform({action:'skip'}))onboardingElement('dialog').close();}
async function onboardingResumeSetup(){await openOnboarding();await onboardingPerform({action:'resume'});}
function onboardingConfigureModel(){onboardingReturnFromModel=true;onboardingElement('dialog').close();openModelSettings();}
document.addEventListener('DOMContentLoaded',()=>{
  const overview=document.querySelector('.knowledge-overview');if(overview)overview.after(onboardingElement('welcome'));
  onboardingElement('dialog').addEventListener('close',()=>{++onboardingGeneration;onboardingBusy=false;});
  for(const id of ['roots','exclusions'])onboardingElement(id).addEventListener('input',()=>{onboardingSourcesDirty=true;});
  document.getElementById('model-settings').addEventListener('close',()=>{if(onboardingReturnFromModel){onboardingReturnFromModel=false;openOnboarding();}});
  const generation=onboardingGeneration;
  onboardingRequest().then(data=>{if(generation!==onboardingGeneration)return;onboardingData=data;renderOnboarding();}).catch(()=>{});
});
document.addEventListener('selfos-language',()=>renderOnboarding());
document.addEventListener('selfos-import-finished',()=>{const generation=onboardingGeneration;onboardingRequest().then(data=>{if(generation!==onboardingGeneration)return;onboardingData=data;renderOnboarding();}).catch(()=>{});});
