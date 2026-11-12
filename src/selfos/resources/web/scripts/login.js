
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
