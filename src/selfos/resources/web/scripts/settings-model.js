
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
  document.getElementById('current-model').textContent=c.provider+' · '+(c.model||'默认 Claude 模型');
  document.getElementById('model-status').textContent='代理来源：'+c.proxy_source+' '+JSON.stringify(c.effective_proxy)+'\n密钥：'+(c.has_api_key?'已配置':'未配置');
}
async function modelRequest(url,body) {
  const r=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await r.json();if(!r.ok)throw new Error(data.error||'请求失败');return data;
}
async function openModelSettings() {
  document.getElementById('model-settings').showModal();
  try {
    const c=await modelRequest('/__model_settings__');
    for(const [id,key] of [['model-provider','provider'],['model-base','base_url'],['model-name','model'],['model-proxy-mode','proxy_mode'],['model-proxy-url','proxy_url']])document.getElementById(id).value=c[key];
    document.getElementById('model-name').value=c.model||(c.provider==='anthropic'?'claude-haiku-4-5-20251001':'');
    document.getElementById('model-key').value='';document.getElementById('model-clear-key').checked=false;
    updateModelProxy();showCurrentModel(c);
  }catch(e){document.getElementById('model-status').textContent=e.message;}
}
async function saveModelSettings(test) {
  const form=document.querySelector('#model-settings form');if(!form.reportValidity())return;
  const buttons=[...form.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
  try {
    const c=await modelRequest('/__model_settings__',{provider:document.getElementById('model-provider').value,base_url:document.getElementById('model-base').value,model:document.getElementById('model-name').value,api_key:document.getElementById('model-key').value,clear_api_key:document.getElementById('model-clear-key').checked,proxy_mode:document.getElementById('model-proxy-mode').value,proxy_url:document.getElementById('model-proxy-url').value});
    document.getElementById('model-key').value='';document.getElementById('model-clear-key').checked=false;showCurrentModel(c);
    if(test){document.getElementById('model-status').textContent='正在测试网络、认证与结构化输出（发送一条测试请求）…';const r=await modelRequest('/__model_test__',{});document.getElementById('model-status').textContent=r.message;}
  }catch(e){document.getElementById('model-status').textContent=e.message;}
  finally{buttons.forEach(b=>b.disabled=false);}
}
document.addEventListener('DOMContentLoaded',()=>{
  const header=document.querySelector('.header-btns');
  if(header)header.append(document.getElementById('model-settings-entry'));
  const languageButton=document.getElementById('lang-toggle');
  if(languageButton){languageButton.hidden=true;languageButton.style.display='none';document.getElementById('app-settings').append(languageButton);}
  modelRequest('/__model_settings__').then(showCurrentModel).catch(()=>{document.getElementById('current-model').textContent='启动本地服务后配置模型';});
});
