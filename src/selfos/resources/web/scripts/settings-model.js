(function(window){
'use strict';
window.selfosUI.register('settings',()=>{
const modelClosed=new Set();
const cleanups=[];
const requests=new Set();
const draftFields=['model-provider','model-base','model-name','model-proxy-mode','model-proxy-url'];
let remountDraft=null;
function on(node,type,listener){node?.addEventListener?.(type,listener);cleanups.push(()=>node?.removeEventListener?.(type,listener));}

function openAppSettings() {
  window.selfosI18n.populateLanguageSelect('settings-language');
  document.getElementById('app-settings').showModal();
}
function setSettingsLanguage(value) {window.selfosI18n.setLocale(value);}
function updateModelProxy() {
  document.getElementById('model-proxy-row').hidden=document.getElementById('model-proxy-mode').value!=='manual';
}
function changeModelProvider() {
  invalidateModelList();
  const openai=document.getElementById('model-provider').value==='openai';
  document.getElementById('model-base').value=openai?'https://api.openai.com/v1':'https://api.anthropic.com';
  document.getElementById('model-name').value=openai?'gpt-4.1-mini':'claude-haiku-4-5-20251001';
  document.getElementById('model-key').value='';
}
function modelStatus(key,params={}){window.selfosI18n.bindText('model-status','ui.model.'+key,params);}
function showCurrentModel(c) {
 window.selfosI18n.bindText('current-model','ui.model.current',()=>({provider:c.provider,model:c.model||window.selfosI18n.t('ui.model.default')}));
 modelStatus('proxy_status',()=>({source:c.proxy_source,proxy:JSON.stringify(c.effective_proxy),key:window.selfosI18n.t(c.has_api_key?'ui.model.configured':'ui.model.unconfigured')}));
}
async function modelRequest(url,body) {
  const controller=new AbortController();requests.add(controller);
  try {
  const r=await fetch(url,{signal:controller.signal,...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
  const data=await r.json();if(!r.ok){const error=new Error('model_request_failed');error.code=data.code;throw error;}return data;
  }finally{requests.delete(controller);}
}
let modelSettingsGeneration=0;
let modelListGeneration=0;
function modelDraft() {
  return {provider:document.getElementById('model-provider').value,base_url:document.getElementById('model-base').value,api_key:document.getElementById('model-key').value,clear_api_key:document.getElementById('model-clear-key').checked,proxy_mode:document.getElementById('model-proxy-mode').value,proxy_url:document.getElementById('model-proxy-url').value};
}
function modelListStatus(key,params={}){window.selfosI18n.bindText('model-list-status','ui.model.'+key,params);}
function invalidateModelList() {
  ++modelListGeneration;
  const select=document.getElementById('model-available');select.hidden=true;select.replaceChildren?.();
  document.getElementById('model-load-models').disabled=false;
  modelListStatus('list_hint');
}
function modelDiscoveryDraftChanged(event) {
  if(['model-provider','model-base','model-key','model-clear-key','model-proxy-mode','model-proxy-url'].includes(event.target.id))invalidateModelList();
}
function chooseAvailableModel() {
  const select=document.getElementById('model-available');
  if(select.value)document.getElementById('model-name').value=select.value;
}
async function loadAvailableModels() {
  const dialog=document.getElementById('model-settings'),button=document.getElementById('model-load-models');
  if(button.disabled||!dialog.open)return;
  for(const id of ['model-base','model-proxy-url'])if(!document.getElementById(id).reportValidity())return;
  invalidateModelList();
  const generation=modelListGeneration,settingsGeneration=modelSettingsGeneration,draft=modelDraft(),fingerprint=JSON.stringify(draft);
  const current=()=>generation===modelListGeneration&&settingsGeneration===modelSettingsGeneration&&dialog.open&&fingerprint===JSON.stringify(modelDraft());
  button.disabled=true;modelListStatus('list_loading');
  try {
    const result=await modelRequest('/__model_list__',draft);
    if(!current())return;
    if(!Array.isArray(result.models)||result.models.some(name=>typeof name!=='string'||!name))throw new Error('invalid_model_list');
    if(!result.models.length){modelListStatus('list_empty');return;}
    const select=document.getElementById('model-available'),placeholder=document.createElement('option');placeholder.value='';
    window.selfosI18n.bindText(placeholder,'ui.model.choose_model');select.replaceChildren(placeholder);
    for(const name of result.models){const option=document.createElement('option');option.value=name;option.textContent=name;select.append(option);}
    select.hidden=false;modelListStatus('list_loaded',{count:result.models.length});
  }catch(error){if(current())modelListStatus(error.code==='model_list_unsupported'?'list_unsupported':error.code==='model_list_invalid'?'list_invalid':'list_failed');}
  finally{if(generation===modelListGeneration)button.disabled=false;}
}
async function openModelSettings() {
  invalidateModelList();
  const generation=++modelSettingsGeneration;
  document.getElementById('model-settings').showModal();
  const controls=[...document.querySelector('#model-settings form').querySelectorAll('input,select,button:not([data-i18n="ui.model.close"])')];
  controls.forEach(control=>control.disabled=true);
  window.selfosI18n.bindText('model-status','ui.import_settings.loading_settings');
  try {
    const c=await modelRequest('/__model_settings__');
    if(generation!==modelSettingsGeneration||!document.getElementById('model-settings').open)return;
    for(const [id,key] of [['model-provider','provider'],['model-base','base_url'],['model-name','model'],['model-proxy-mode','proxy_mode'],['model-proxy-url','proxy_url']])document.getElementById(id).value=c[key];
    document.getElementById('model-name').value=c.model||(c.provider==='anthropic'?'claude-haiku-4-5-20251001':'');
    document.getElementById('model-key').value='';document.getElementById('model-clear-key').checked=false;
    updateModelProxy();showCurrentModel(c);
  }catch(e){if(generation===modelSettingsGeneration)modelStatus('request_failed');}
  finally{if(generation===modelSettingsGeneration)controls.forEach(control=>control.disabled=false);}
}
async function saveModelSettings(test) {
  const form=document.querySelector('#model-settings form');if(!form.reportValidity())return;
  const generation=modelSettingsGeneration;
  invalidateModelList();
  const buttons=[...form.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
  try {
    const c=await modelRequest('/__model_settings__',{provider:document.getElementById('model-provider').value,base_url:document.getElementById('model-base').value,model:document.getElementById('model-name').value,api_key:document.getElementById('model-key').value,clear_api_key:document.getElementById('model-clear-key').checked,proxy_mode:document.getElementById('model-proxy-mode').value,proxy_url:document.getElementById('model-proxy-url').value});
    if(generation!==modelSettingsGeneration)return;
    document.getElementById('model-key').value='';document.getElementById('model-clear-key').checked=false;showCurrentModel(c);
    if(test){modelStatus('testing');const r=await modelRequest('/__model_test__',{});if(generation===modelSettingsGeneration)modelStatus(r.ok?'passed':'request_failed');}
  }catch(e){if(generation===modelSettingsGeneration)modelStatus('request_failed');}
  finally{if(generation===modelSettingsGeneration)buttons.forEach(b=>b.disabled=false);}
}
function init(document){
  if(remountDraft){
    for(const [id,value]of Object.entries(remountDraft.values))document.getElementById(id).value=value;
    const form=document.querySelector('#model-settings form');form.querySelectorAll('input,select,button').forEach(control=>control.disabled=false);
    document.getElementById('model-key').value='';document.getElementById('model-clear-key').checked=false;
    for(const [id,open]of [['model-settings',remountDraft.modelOpen],['app-settings',remountDraft.appOpen]])if(open){const dialog=document.getElementById(id);if(dialog.open)dialog.close();dialog.showModal();}
    updateModelProxy();remountDraft=null;
  }
  const actions={
    'settings.open':['click',openAppSettings],
    'settings.language':['change',(_,node)=>setSettingsLanguage(node.value)],
    'settings.model':['click',()=>{document.getElementById('app-settings').close();openModelSettings();}],
    'settings.privacy':['click',()=>window.selfosUI.module('privacy').open()],
    'settings.setup':['click',()=>{document.getElementById('app-settings').close();window.selfosUI.module('onboarding').resume();}],
    'settings.close':['click',()=>document.getElementById('app-settings').close()],
    'settings.save':['submit',()=>saveModelSettings(false)],
    'settings.provider':['change',changeModelProvider],
    'settings.models':['click',loadAvailableModels],
    'settings.choose':['change',chooseAvailableModel],
    'settings.proxy':['change',updateModelProxy],
    'settings.test':['click',()=>saveModelSettings(true)],
    'settings.model-close':['click',()=>document.getElementById('model-settings').close()]
  };
  function action(event){
    const node=event.target.closest?.('[data-selfos-action]');
    if(!node||!document.contains(node)||!node.closest('#app-settings,#model-settings,#model-settings-entry'))return;
    if(!Object.hasOwn(actions,node.dataset.selfosAction))return;const entry=actions[node.dataset.selfosAction];
    if(!entry||entry[0]!==event.type)return;
    event.preventDefault();entry[1](event,node);
  }
  for(const type of ['click','change','submit'])on(document,type,action);
  const form=document.querySelector('#model-settings form');
  on(form,'input',modelDiscoveryDraftChanged);on(form,'change',modelDiscoveryDraftChanged);
  on(document.getElementById('model-settings'),'close',()=>{invalidateModelList();for(const callback of modelClosed)callback();});
  const settings=document.getElementById('app-settings');
  on(settings,'close',()=>{
    if(!document.querySelector('dialog[open]'))document.querySelector('#model-settings-entry button')?.focus();
  });
  const header=document.querySelector('.header-btns');
  if(header)header.append(document.getElementById('model-settings-entry'));
  const languageButton=document.getElementById('lang-toggle');
  if(languageButton){languageButton.hidden=true;languageButton.style.display='none';document.getElementById('app-settings').append(languageButton);}
  const generation=modelSettingsGeneration;
  modelRequest('/__model_settings__').then(c=>{if(generation===modelSettingsGeneration)showCurrentModel(c);}).catch(()=>{if(generation===modelSettingsGeneration)window.selfosI18n.bindText('current-model','ui.model.start_server');});
}
function teardown(){
  remountDraft={values:Object.fromEntries(draftFields.map(id=>[id,document.getElementById(id).value])),modelOpen:document.getElementById('model-settings').open,appOpen:document.getElementById('app-settings').open};
  document.getElementById('model-key').value='';document.getElementById('model-clear-key').checked=false;
  ++modelSettingsGeneration;++modelListGeneration;
  for(const request of requests)request.abort();requests.clear();
  cleanups.splice(0).reverse().forEach(cleanup=>cleanup());modelClosed.clear();
}
return {onModelClosed(callback){modelClosed.add(callback);return()=>modelClosed.delete(callback);},busy:()=>requests.size>0,open:openAppSettings,openModel:openModelSettings,saveModel:saveModelSettings,openAppSettings,setSettingsLanguage,updateModelProxy,changeModelProvider,modelStatus,showCurrentModel,modelRequest,modelDraft,modelListStatus,invalidateModelList,modelDiscoveryDraftChanged,chooseAvailableModel,loadAvailableModels,openModelSettings,saveModelSettings,init,teardown};
},{dependencies:['privacy','request','locale'],roots:['#app-settings','#model-settings','#model-settings-entry']});
for(const [name,method]of Object.entries({openAppSettings:'openAppSettings',setSettingsLanguage:'setSettingsLanguage',updateModelProxy:'updateModelProxy',changeModelProvider:'changeModelProvider',modelStatus:'modelStatus',showCurrentModel:'showCurrentModel',modelRequest:'modelRequest',modelDraft:'modelDraft',modelListStatus:'modelListStatus',invalidateModelList:'invalidateModelList',modelDiscoveryDraftChanged:'modelDiscoveryDraftChanged',chooseAvailableModel:'chooseAvailableModel',loadAvailableModels:'loadAvailableModels',openModelSettings:'openModelSettings',saveModelSettings:'saveModelSettings'})){if(!window[name])window[name]=(...args)=>window.selfosUI.module('settings')[method](...args);}
})(window);
