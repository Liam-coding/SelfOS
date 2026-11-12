
function openAppSettings() {
  window.selfosI18n.populateLanguageSelect('settings-language');
  document.getElementById('app-settings').showModal();
}
function setSettingsLanguage(value) {window.selfosI18n.setLocale(value);}
function updateModelProxy() {
  document.getElementById('model-proxy-row').hidden=document.getElementById('model-proxy-mode').value!=='manual';
}
function changeModelProvider() {
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
  const r=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await r.json();if(!r.ok)throw new Error('model_request_failed');return data;
}
async function openModelSettings() {
  document.getElementById('model-settings').showModal();
  try {
    const c=await modelRequest('/__model_settings__');
    for(const [id,key] of [['model-provider','provider'],['model-base','base_url'],['model-name','model'],['model-proxy-mode','proxy_mode'],['model-proxy-url','proxy_url']])document.getElementById(id).value=c[key];
    document.getElementById('model-name').value=c.model||(c.provider==='anthropic'?'claude-haiku-4-5-20251001':'');
    document.getElementById('model-key').value='';document.getElementById('model-clear-key').checked=false;
    updateModelProxy();showCurrentModel(c);
  }catch(e){modelStatus('request_failed');}
}
async function saveModelSettings(test) {
  const form=document.querySelector('#model-settings form');if(!form.reportValidity())return;
  const buttons=[...form.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
  try {
    const c=await modelRequest('/__model_settings__',{provider:document.getElementById('model-provider').value,base_url:document.getElementById('model-base').value,model:document.getElementById('model-name').value,api_key:document.getElementById('model-key').value,clear_api_key:document.getElementById('model-clear-key').checked,proxy_mode:document.getElementById('model-proxy-mode').value,proxy_url:document.getElementById('model-proxy-url').value});
    document.getElementById('model-key').value='';document.getElementById('model-clear-key').checked=false;showCurrentModel(c);
    if(test){modelStatus('testing');const r=await modelRequest('/__model_test__',{});modelStatus(r.ok?'passed':'request_failed');}
  }catch(e){modelStatus('request_failed');}
  finally{buttons.forEach(b=>b.disabled=false);}
}
document.addEventListener('DOMContentLoaded',()=>{
  const header=document.querySelector('.header-btns');
  if(header)header.append(document.getElementById('model-settings-entry'));
  const languageButton=document.getElementById('lang-toggle');
  if(languageButton){languageButton.hidden=true;languageButton.style.display='none';document.getElementById('app-settings').append(languageButton);}
  modelRequest('/__model_settings__').then(showCurrentModel).catch(()=>{window.selfosI18n.bindText('current-model','ui.model.start_server');});
});
