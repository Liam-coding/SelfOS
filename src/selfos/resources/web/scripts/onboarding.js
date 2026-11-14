(function(window){'use strict';window.selfosUI.register('onboarding',()=>{
const requests=new Set(),cleanups=[];let draft=null,refreshing=null,refreshQueued=false;function on(node,type,callback){node?.addEventListener(type,callback);cleanups.push(()=>node?.removeEventListener(type,callback));}
let onboardingData=null,onboardingGeneration=0,onboardingBusy=false,onboardingSourcesDirty=false,onboardingReturnFromModel=false;
const onboardingElement=id=>document.getElementById('onboarding-'+id);
const onboardingText=(id,key,params={})=>window.selfosI18n.bindText(onboardingElement(id),'onboarding.'+key,params);
async function onboardingRequest(body){
  const controller=new AbortController();requests.add(controller);try{const response=await fetch('/__onboarding__',{signal:controller.signal,...(body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
  const data=await response.json();if(!response.ok){const error=new Error(data.code||'onboarding_unavailable');error.code=data.code;throw error;}return data;}finally{requests.delete(controller);}
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
  if(window.selfosHarness)window.selfosHarness.update(data.sources,data.availability,onboardingSourcesDirty);
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
  refreshing=null;refreshQueued=false;if(!dialog.open)dialog.showModal();onboardingBusy=true;renderOnboarding();onboardingText('status','loading');
  try{const data=await onboardingRequest();if(generation!==onboardingGeneration||!dialog.open)return;onboardingData=data;onboardingText('status','ready');}
  catch(error){if(generation===onboardingGeneration)onboardingText('status','unavailable');}
  finally{if(generation===onboardingGeneration){onboardingBusy=false;renderOnboarding();}}
}

async function onboardingPerform(body){
  if(onboardingBusy||window.selfosReadOnlyDemo)return null;const generation=++onboardingGeneration;refreshing=null;refreshQueued=false;onboardingBusy=true;renderOnboarding();onboardingText('status','loading');
  try{const data=await onboardingRequest(body);if(generation===onboardingGeneration){onboardingData=data;if(body.action==='save_sources')onboardingSourcesDirty=false;renderOnboarding();onboardingText('status','ready');return data;}return null;}
  catch(error){if(generation===onboardingGeneration)onboardingText('status',error.code==='onboarding_import_active'?'import_active':'invalid');return null;}
  finally{if(generation===onboardingGeneration){onboardingBusy=false;renderOnboarding();}}
}
async function onboardingStep(direction){if(!onboardingData)return;const step=onboardingData.progress.step;if(direction>0&&step===1&&onboardingSourcesDirty){if(!await onboardingSaveSources())return;}await onboardingPerform({action:'save_step',step:Math.max(0,Math.min(4,step+direction))});}
async function onboardingSaveSources(){
  const lines=id=>onboardingElement(id).value.split(/\r?\n/).map(line=>line.trim()).filter(Boolean);
  const roots=lines('roots'),native=window.selfosHarness?window.selfosHarness.entries():[],previous=onboardingData?.sources||{};
  const sources=native.length||previous.version===2?{version:2,entries:[...roots.map(path=>({kind:'directory',path})),...native],exclusions:lines('exclusions'),project_exclusions:lines('project-exclusions')}:{roots,exclusions:lines('exclusions')};
  if(previous.privacy_exclusions)sources.privacy_exclusions=previous.privacy_exclusions;
  return await onboardingPerform({action:'save_sources',sources});
}
async function onboardingPreview(tier){await onboardingPerform({action:'preview',tier});}
async function onboardingNewAllowance(){if(onboardingData?.preview)await onboardingPerform({action:'new_allowance',preview_id:onboardingData.preview.id});}
async function onboardingStart(){if(!onboardingData?.preview)return;const data=await onboardingPerform({action:'start',preview_id:onboardingData.preview.id});if(data?.stream_url){onboardingElement('dialog').close();window.selfosUI.module('jobs').start(false,true,false,data.stream_url);}}
async function onboardingSkip(){if(await onboardingPerform({action:'skip'}))onboardingElement('dialog').close();}
async function onboardingResumeSetup(){await openOnboarding();await onboardingPerform({action:'resume'});}
function onboardingConfigureModel(){onboardingReturnFromModel=true;onboardingElement('dialog').close();window.selfosUI.module('settings').openModel();}

function refresh(){
 if(refreshing){refreshQueued=true;return refreshing;}const generation=onboardingGeneration;
 refreshing=onboardingRequest().then(data=>{if(generation!==onboardingGeneration)return;onboardingData=data;renderOnboarding();}).catch(()=>{}).finally(()=>{if(generation===onboardingGeneration){refreshing=null;if(refreshQueued){refreshQueued=false;refresh();}}});return refreshing;
}
function close(){onboardingElement('dialog').close();}
function action(event){const node=event.target.closest?.('[data-selfos-action]');if(!node||!document.contains(node)||!node.closest('#onboarding-dialog,#onboarding-welcome'))return;
 const actions={'onboarding.open':openOnboarding,'onboarding.close':close,'onboarding.sources':onboardingSaveSources,'onboarding.model':onboardingConfigureModel,'onboarding.preview':()=>onboardingPreview('sample'),'onboarding.start':onboardingStart,'onboarding.allowance':onboardingNewAllowance,'onboarding.progress':()=>{close();window.selfosUI.module('jobs').recover();},'onboarding.browse':()=>{close();window.selfosUI.module('knowledge').browse('all');},'onboarding.more':()=>onboardingPreview('more'),'onboarding.back':()=>onboardingStep(-1),'onboarding.skip':onboardingSkip,'onboarding.next':()=>onboardingStep(1)};
 if(!Object.hasOwn(actions,node.dataset.selfosAction))return;event.preventDefault();actions[node.dataset.selfosAction]();
}
function init(){
 ++onboardingGeneration;
 const overview=document.querySelector('.knowledge-overview');if(overview)overview.after(onboardingElement('welcome'));
 on(document,'click',action);on(onboardingElement('dialog'),'close',()=>{++onboardingGeneration;onboardingBusy=false;refreshing=null;refreshQueued=false;});
 for(const id of ['roots','exclusions'])on(onboardingElement(id),'input',()=>{onboardingSourcesDirty=true;});
 cleanups.push(window.selfosUI.module('settings').onModelClosed(()=>{if(onboardingReturnFromModel){onboardingReturnFromModel=false;openOnboarding();}}));
 on(document,'selfos-language',renderOnboarding);
 cleanups.push(window.selfosUI.module('jobs').subscribe(state=>{if(state.kind==='knowledge'&&state.event==='finished')refresh();}));
 if(draft){onboardingElement('roots').value=draft.roots;onboardingElement('exclusions').value=draft.exclusions;if(draft.open){const dialog=onboardingElement('dialog');if(dialog.open)dialog.close();dialog.showModal();}draft=null;}renderOnboarding();refresh();
}
function teardown(){draft={roots:onboardingElement('roots').value,exclusions:onboardingElement('exclusions').value,open:onboardingElement('dialog').open};++onboardingGeneration;onboardingBusy=false;refreshing=null;refreshQueued=false;for(const controller of requests)controller.abort();requests.clear();cleanups.splice(0).reverse().forEach(cleanup=>cleanup());}
return {open:openOnboarding,close,resume:onboardingResumeSetup,refresh,step:onboardingStep,saveSources:onboardingSaveSources,preview:onboardingPreview,newAllowance:onboardingNewAllowance,start:onboardingStart,skip:onboardingSkip,configureModel:onboardingConfigureModel,init,teardown,busy:()=>requests.size>0};
},{dependencies:['jobs','settings','knowledge','request','locale'],roots:['#onboarding-dialog','#onboarding-welcome']});
for(const [name,method]of Object.entries({openOnboarding:'open',onboardingResumeSetup:'resume',onboardingStep:'step',onboardingSaveSources:'saveSources',onboardingPreview:'preview',onboardingNewAllowance:'newAllowance',onboardingStart:'start',onboardingSkip:'skip',onboardingConfigureModel:'configureModel'}))if(!window[name])window[name]=(...args)=>window.selfosUI.module('onboarding')[method](...args);
})(window);
