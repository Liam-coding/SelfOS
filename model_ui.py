"""Model settings shared by generated and existing dashboards."""
CONTROLS = r'''
<style>
#model-settings { margin:auto!important; background:var(--bg,#fff)!important; padding:28px!important; max-height:calc(100vh - 40px); overflow:auto; box-shadow:0 24px 80px rgba(19,44,88,.2); }
#model-settings::backdrop,#app-settings::backdrop { background:rgba(31,42,66,.3); backdrop-filter:blur(6px); }
#model-settings h3 { font-size:22px; margin-bottom:14px; }
#model-settings p { font-size:13px; line-height:1.6; margin:12px 0; }
#model-settings input:not([type=checkbox]),#model-settings select { background:var(--surface,#fff); color:var(--text,#222); border:1px solid var(--line,#ccc); border-radius:8px; padding:9px; margin-top:5px; max-width:100%; }
#model-settings button { padding:10px 14px; border:1px solid var(--line,#ccc); border-radius:10px; margin:4px 2px; cursor:pointer; }
#model-settings button[type=submit] { background:var(--blue,#2474db); color:white; }
#model-settings button:disabled { opacity:.5; cursor:wait; }
#model-status { overflow-wrap:anywhere; color:var(--muted,#555); }
</style>
<div id="model-settings-entry" style="display:inline-flex">
  <button class="harvest-btn" onclick="openAppSettings()" data-zh="⚙ 设置" data-en="⚙ Settings">⚙ Settings</button>
</div>
<dialog id="app-settings" style="margin:auto;background:var(--bg,#fff);color:var(--text,#222);border:1px solid var(--line,#ccc);border-radius:16px;padding:28px;width:min(440px,90vw)">
  <h3 data-zh="设置" data-en="Settings">Settings</h3>
  <p style="margin:20px 0"><label><span data-zh="语言" data-en="Language">Language</span>
    <select id="settings-language" onchange="setSettingsLanguage(this.value)" style="padding:10px;border-radius:8px"><option value="en">English</option><option value="zh">中文</option></select></label></p>
  <button class="harvest-btn" onclick="document.getElementById('app-settings').close();openModelSettings()" data-zh="模型与网络" data-en="Model and network">Model and network</button>
  <p id="current-model" style="font-size:12px;margin:16px 0" aria-live="polite"></p>
  <button class="harvest-btn" onclick="document.getElementById('app-settings').close()" data-zh="关闭" data-en="Close">Close</button>
</dialog>
<dialog id="model-settings" style="background:var(--surface,#fff);color:var(--text,#222);border:1px solid var(--line,#ccc);border-radius:16px;padding:24px;width:min(540px,90vw)">
  <h3 data-zh="模型与网络" data-en="Model and network">模型与网络</h3>
  <p data-zh="知识整理、项目精炼和聊天共用此配置。密钥仅保存在本地服务，输入留空保留已有密钥。" data-en="Imports, project refinement and chat share this configuration. Keys stay on the local server. Leave the key blank to keep it.">知识整理、项目精炼和聊天共用此配置。密钥仅保存在本地服务，输入留空保留已有密钥。</p>
  <form onsubmit="event.preventDefault();saveModelSettings(false)">
    <p><label><span data-zh="接口" data-en="Interface">接口</span> <select id="model-provider" onchange="changeModelProvider()"><option value="anthropic">Anthropic Messages</option><option value="openai">OpenAI-compatible</option></select></label></p>
    <p><label>Base URL <input id="model-base" type="url" required style="width:100%"></label></p>
    <p><label><span data-zh="模型名称" data-en="Model name">模型名称</span> <input id="model-name" required placeholder="例如 claude-haiku-4-5-20251001 / gpt-4.1-mini" style="width:100%"></label></p>
    <p><label>API key <input id="model-key" type="password" autocomplete="new-password" placeholder="留空保留已有密钥" style="width:100%"></label></p>
    <p><label><input id="model-clear-key" type="checkbox"><span data-zh="清除已有密钥（本地模型可不填）" data-en="Clear saved key (optional for local models)">清除已有密钥（本地模型可不填）</span></label></p>
    <p><label><span data-zh="代理" data-en="Proxy">代理</span> <select id="model-proxy-mode" onchange="updateModelProxy()"><option value="auto" data-zh="自动：环境变量 / 系统代理" data-en="Auto: environment / system proxy">自动：环境变量 / 系统代理</option><option value="manual" data-zh="手动 HTTP(S) 代理" data-en="Manual HTTP(S) proxy">手动 HTTP(S) 代理</option><option value="direct" data-zh="直连" data-en="Direct">直连</option></select></label></p>
    <p id="model-proxy-row"><label><span data-zh="代理地址" data-en="Proxy URL">代理地址</span> <input id="model-proxy-url" placeholder="http://127.0.0.1:7890" style="width:100%"></label></p>
    <p data-zh="本地模型默认直连。自动模式优先环境变量，Windows 下再读取系统静态代理；暂不执行 PAC 脚本。" data-en="Local models connect directly. Auto uses environment variables, then the Windows static proxy. PAC scripts are not supported.">本地模型默认直连。自动模式优先环境变量，Windows 下再读取系统静态代理；暂不执行 PAC 脚本。</p>
    <p id="model-status" role="status" style="white-space:pre-wrap"></p>
    <button type="submit" data-zh="保存" data-en="Save">保存</button>
    <button type="button" onclick="saveModelSettings(true)" data-zh="保存并测试连接" data-en="Save and test connection">保存并测试连接</button>
    <button type="button" onclick="document.getElementById('model-settings').close()" data-zh="关闭" data-en="Close">关闭</button>
  </form>
</dialog>
<script>
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
</script>
'''
