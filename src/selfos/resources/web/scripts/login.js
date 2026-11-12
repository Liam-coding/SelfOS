
let authMode='ready';
document.body.classList.toggle('auth-dark',localStorage.getItem('selfos-theme')==='dark');
function authLanguage(value){window.selfosI18n.setLocale(value);document.getElementById('auth-language').value=window.selfosI18n.locale;}
window.selfosI18n.populateLanguageSelect('auth-language');
translateAuth();
document.getElementById('auth-language').onchange=e=>authLanguage(e.target.value);
fetch('/auth/status').then(r=>r.json()).then(data=>{
  if(data.authenticated){location.replace('/');return;}
  authMode=data.state;const setup=authMode==='setup';
  document.getElementById('auth-form').hidden=authMode==='locked';document.getElementById('auth-recovery').hidden=authMode!=='locked';
  document.getElementById('auth-heading').dataset.i18n=authMode==='locked'?'auth.locked':setup?'auth.setup':'auth.title';
  document.getElementById('auth-description').dataset.i18n=setup?'auth.setup_description':'auth.description';
  document.getElementById('auth-submit').dataset.i18n=setup?'auth.setup':'auth.login';
  document.getElementById('auth-confirm-row').hidden=!setup;document.getElementById('auth-confirm').required=setup;
  document.getElementById('auth-length').hidden=!setup;document.getElementById('auth-password').autocomplete=setup?'new-password':'current-password';translateAuth();
}).catch(()=>authStatus('auth-status','network'));
document.getElementById('auth-form').onsubmit=async e=>{
  e.preventDefault();const button=document.getElementById('auth-submit'),status=document.getElementById('auth-status'),password=document.getElementById('auth-password').value;
  if(authMode==='setup'&&password!==document.getElementById('auth-confirm').value){authStatus(status,'mismatch');return;}
  button.disabled=true;authStatus(status,'working');
  try{await authRequest('/auth/'+(authMode==='setup'?'setup':'login'),{password});location.replace('/');}catch(error){authStatus(status,error.code||'auth_error');document.getElementById('auth-password').value='';document.getElementById('auth-confirm').value='';}finally{button.disabled=false;}
};
