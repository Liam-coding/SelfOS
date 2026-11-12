
const modelMessages = __MODEL_MESSAGES__;
let modelView = {config:null, status:null, unavailable:false};
function modelText(key) {
  const locale=document.documentElement.lang==='zh'?'zh':'en';
  return modelMessages[locale][key] || modelMessages.en[key] || key;
}
function refreshModelLanguage() {
  document.getElementById('model-name').placeholder=modelText('namePlaceholder');
  document.getElementById('model-key').placeholder=modelText('keyPlaceholder');
  if(modelView.config) {
    const c=modelView.config;
    document.getElementById('current-model').textContent=c.provider+' · '+(c.model||modelText('defaultModel'));
  } else if(modelView.unavailable) document.getElementById('current-model').textContent=modelText('unavailable');
  if(modelView.status) {
    const s=modelView.status;
    document.getElementById('model-status').textContent=s.key?modelText(s.key):s.error?modelText('requestFailed')+': '+s.error:s.text;
  } else if(modelView.config) {
    const c=modelView.config;
    document.getElementById('model-status').textContent=modelText('proxySource')+': '+c.proxy_source+' '+JSON.stringify(c.effective_proxy)+'\n'+modelText('key')+': '+modelText(c.has_api_key?'configured':'notConfigured');
  }
}
function setModelStatus(status) {modelView.status=status;refreshModelLanguage();}
document.addEventListener('selfos-language',refreshModelLanguage);
function openAppSettings() {
  document.getElementById('settings-language').value=document.documentElement.lang==='zh'?'zh':'en';
  document.getElementById('app-settings').showModal();
}
function setSettingsLanguage(value) {
  lang=value==='zh'?'zh':'en';
  applyLanguage();
}
function updateModelProxy() {
  document.getElementById('model-proxy-row').hidden=document.getElementById('model-proxy-mode').value!=='manual';
}
function changeModelProvider() {
  const openai=document.getElementById('model-provider').value==='openai';
  document.getElementById('model-base').value=openai?'https://api.openai.com/v1':'https://api.anthropic.com';
  document.getElementById('model-name').value=openai?'gpt-4.1-mini':'claude-haiku-4-5-20251001';
  document.getElementById('model-key').value='';
}
function showCurrentModel(c) {
  modelView.config=c;modelView.status=null;modelView.unavailable=false;refreshModelLanguage();
}
async function modelRequest(url,body) {
  const r=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await r.json();if(!r.ok)throw new Error(data.error||'HTTP '+r.status);return data;
}
async function openModelSettings() {
  document.getElementById('model-settings').showModal();
  try {
    const c=await modelRequest('/__model_settings__');
    for(const [id,key] of [['model-provider','provider'],['model-base','base_url'],['model-name','model'],['model-proxy-mode','proxy_mode'],['model-proxy-url','proxy_url']])document.getElementById(id).value=c[key];
    document.getElementById('model-name').value=c.model||(c.provider==='anthropic'?'claude-haiku-4-5-20251001':'');
    document.getElementById('model-key').value='';document.getElementById('model-clear-key').checked=false;
    updateModelProxy();showCurrentModel(c);
  }catch(e){setModelStatus({error:e.message});}
}
async function saveModelSettings(test) {
  const form=document.querySelector('#model-settings form');if(!form.reportValidity())return;
  const buttons=[...form.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
  try {
    const c=await modelRequest('/__model_settings__',{provider:document.getElementById('model-provider').value,base_url:document.getElementById('model-base').value,model:document.getElementById('model-name').value,api_key:document.getElementById('model-key').value,clear_api_key:document.getElementById('model-clear-key').checked,proxy_mode:document.getElementById('model-proxy-mode').value,proxy_url:document.getElementById('model-proxy-url').value});
    document.getElementById('model-key').value='';document.getElementById('model-clear-key').checked=false;showCurrentModel(c);
    if(test){setModelStatus({key:'testing'});const r=await modelRequest('/__model_test__',{});setModelStatus(r.ok?{key:'passed'}:{text:r.message});}
  }catch(e){setModelStatus({error:e.message});}
  finally{buttons.forEach(b=>b.disabled=false);}
}
document.addEventListener('DOMContentLoaded',()=>{
  const header=document.querySelector('.header-btns');
  if(header)header.append(document.getElementById('model-settings-entry'));
  const languageButton=document.getElementById('lang-toggle');
  if(languageButton){languageButton.hidden=true;languageButton.style.display='none';document.getElementById('app-settings').append(languageButton);}
  refreshModelLanguage();
  modelRequest('/__model_settings__').then(showCurrentModel).catch(()=>{modelView.unavailable=true;refreshModelLanguage();});
});
