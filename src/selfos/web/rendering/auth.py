"""web / rendering / auth responsibilities."""
import json

def resources():
    from selfos.paths import resource
    root=resource('locales')
    return {code:json.loads((root/folder/'auth.json').read_text(encoding='utf-8')) for code,folder in [('en','en'),('zh','zh-CN')]}


STYLE=r'''<style>
.auth-card { max-width:440px; margin:auto; background:var(--panel,#fff); color:var(--text,#192235); border:1px solid var(--line,#e3e8f0); border-radius:24px; padding:32px; box-shadow:0 20px 60px rgba(37,65,122,.10); }
.auth-card h1,.auth-card h2 { font-size:25px; letter-spacing:-.7px; margin:18px 0 12px; }
.auth-card p { color:var(--muted,#5f6b83); font-size:13px; line-height:1.8; margin:12px 0; }
.auth-card label { display:block; font-size:13px; margin:18px 0 6px; }
.auth-card input,.auth-card select { width:100%; box-sizing:border-box; border:1px solid var(--line,#dce3ed); background:var(--soft,#edf2fa); color:inherit; border-radius:12px; padding:12px; font:inherit; margin-top:7px; }
.auth-card button { min-height:42px; padding:11px 16px; border:0; border-radius:12px; cursor:pointer; font:inherit; background:var(--blue,#007aff); color:white; margin-top:16px; }
.auth-card button:disabled { opacity:.5; cursor:wait; }
.auth-card code { display:block; background:var(--soft,#edf2fa); padding:14px; border-radius:12px; font-size:12px; overflow-wrap:anywhere; }
.auth-card [role=status] { min-height:22px; overflow-wrap:anywhere; }
.auth-card :focus-visible { outline:3px solid #69aaff; outline-offset:3px; }
body.auth-dark { --panel:#192438; --soft:#202f45; --text:#e9eef8; --muted:#8b99af; --line:rgba(142,170,216,.13); background:#101722; }
#auth-change { width:min(440px,calc(100vw - 32px)); max-height:calc(100dvh - 32px); overflow:auto; }
#auth-change::backdrop { background:rgba(31,42,66,.3); backdrop-filter:blur(6px); }
</style>'''


SCRIPT=r'''<script>
const authLocales=__LOCALES__;
const authText=key=>(authLocales[document.documentElement.lang==='zh'?'zh':'en'][key]||authLocales.en[key]||key);
function translateAuth() {document.querySelectorAll('[data-auth-key]').forEach(e=>e.textContent=authText(e.dataset.authKey));}
async function authRequest(path,body) {
  let response;
  try {response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});}catch(e){throw new Error(authText('network'));}
  const data=await response.json();if(!response.ok){const error=new Error(authText(data.error_code||'auth_error'));error.status=response.status;throw error;}return data;
}
document.addEventListener('selfos-language',translateAuth);
document.addEventListener('DOMContentLoaded',translateAuth);
</script>'''


def script():return SCRIPT.replace('__LOCALES__',json.dumps(resources(),ensure_ascii=False))


def login_page():
    return r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SelfOS — Login</title>
<style>body{margin:0;padding:36px 16px;min-height:100dvh;box-sizing:border-box;display:grid;place-items:center;background:radial-gradient(ellipse at 10% 0%,#e8f0ff,transparent 55%),#f6f7fb;font:14px system-ui,sans-serif}*{box-sizing:border-box}[hidden]{display:none!important}.auth-card{width:100%}</style>'''+STYLE+r'''</head><body><main class="auth-card">
<strong style="font-size:28px;letter-spacing:-1px">SelfOS</strong>
<select id="auth-language" aria-label="Language"><option value="en">English</option><option value="zh">中文</option></select>
<h1 id="auth-heading" data-auth-key="title"></h1><p id="auth-description" data-auth-key="description"></p>
<form id="auth-form" hidden><label><span data-auth-key="password"></span><input id="auth-password" type="password" autocomplete="current-password" required maxlength="1024"></label>
<label id="auth-confirm-row" hidden><span data-auth-key="confirm"></span><input id="auth-confirm" type="password" autocomplete="new-password" maxlength="1024"></label>
<p id="auth-length" data-auth-key="length" hidden></p><button id="auth-submit" type="submit" data-auth-key="login"></button></form>
<section id="auth-recovery" hidden><p data-auth-key="recovery"></p><code>python selfos_auth.py reset</code></section>
<p id="auth-status" role="status"></p></main>'''+script()+r'''<script>
let authMode='ready';
document.body.classList.toggle('auth-dark',localStorage.getItem('selfos-theme')==='dark');
function authLanguage(value){document.documentElement.lang=value==='zh'?'zh':'en';localStorage.setItem('selfos-lang',document.documentElement.lang);document.getElementById('auth-language').value=document.documentElement.lang;translateAuth();}
authLanguage(localStorage.getItem('selfos-lang'));
document.getElementById('auth-language').onchange=e=>authLanguage(e.target.value);
fetch('/auth/status').then(r=>r.json()).then(data=>{
  if(data.authenticated){location.replace('/');return;}
  authMode=data.state;const setup=authMode==='setup';
  document.getElementById('auth-form').hidden=authMode==='locked';document.getElementById('auth-recovery').hidden=authMode!=='locked';
  document.getElementById('auth-heading').dataset.authKey=authMode==='locked'?'locked':setup?'setup':'title';
  document.getElementById('auth-description').dataset.authKey=setup?'setup_description':'description';
  document.getElementById('auth-submit').dataset.authKey=setup?'setup':'login';
  document.getElementById('auth-confirm-row').hidden=!setup;document.getElementById('auth-confirm').required=setup;
  document.getElementById('auth-length').hidden=!setup;document.getElementById('auth-password').autocomplete=setup?'new-password':'current-password';translateAuth();
}).catch(()=>document.getElementById('auth-status').textContent=authText('network'));
document.getElementById('auth-form').onsubmit=async e=>{
  e.preventDefault();const button=document.getElementById('auth-submit'),status=document.getElementById('auth-status'),password=document.getElementById('auth-password').value;
  if(authMode==='setup'&&password!==document.getElementById('auth-confirm').value){status.textContent=authText('mismatch');return;}
  button.disabled=true;status.textContent=authText('working');
  try{await authRequest('/auth/'+(authMode==='setup'?'setup':'login'),{password});location.replace('/');}catch(error){status.textContent=error.message;document.getElementById('auth-password').value='';document.getElementById('auth-confirm').value='';}finally{button.disabled=false;}
};
</script></body></html>'''


def account_controls():
    return STYLE+r'''<div id="auth-account-buttons"><button class="harvest-btn" onclick="document.getElementById('app-settings').close();document.getElementById('auth-change').showModal()" data-auth-key="change"></button><button class="harvest-btn" onclick="logoutSelfOS()" data-auth-key="logout"></button><p id="auth-account-status" role="status"></p></div>
<dialog id="auth-change" class="auth-card"><h2 data-auth-key="change"></h2><p data-auth-key="change_hint"></p>
<form onsubmit="changeSelfOSPassword(event)"><label><span data-auth-key="current"></span><input id="auth-current" type="password" autocomplete="current-password" required maxlength="1024"></label>
<label><span data-auth-key="new"></span><input id="auth-new" type="password" autocomplete="new-password" required minlength="12" maxlength="1024"></label>
<label><span data-auth-key="confirm"></span><input id="auth-new-confirm" type="password" autocomplete="new-password" required maxlength="1024"></label>
<p id="auth-change-status" role="status"></p><button type="submit" data-auth-key="change"></button><button type="button" onclick="document.getElementById('auth-change').close();document.querySelectorAll('#auth-change input').forEach(e=>e.value='')" data-auth-key="close"></button></form></dialog>'''+script()+r'''<script>
const selfosFetch=window.fetch.bind(window);
window.fetch=async(...args)=>{const response=await selfosFetch(...args);if(response.status===401&&!String(args[0]).includes('/auth/'))location.replace('/login');return response;};
async function logoutSelfOS(){try{await authRequest('/auth/logout',{});location.replace('/login');}catch(e){if(e.status===401){location.replace('/login');return;}document.getElementById('auth-account-status').textContent=e.message;}}
async function changeSelfOSPassword(event){event.preventDefault();const status=document.getElementById('auth-change-status'),password=document.getElementById('auth-new').value;if(password!==document.getElementById('auth-new-confirm').value){status.textContent=authText('mismatch');return;}const button=event.target.querySelector('button[type=submit]');button.disabled=true;try{await authRequest('/auth/change',{current_password:document.getElementById('auth-current').value,password});location.replace('/login');}catch(e){status.textContent=e.message;document.querySelectorAll('#auth-change input').forEach(e=>e.value='');}finally{button.disabled=false;}}
document.addEventListener('DOMContentLoaded',()=>{const settings=document.getElementById('app-settings');if(settings)settings.append(document.getElementById('auth-account-buttons'));translateAuth();});
</script>'''


ACCOUNT_CONTROLS=account_controls()
