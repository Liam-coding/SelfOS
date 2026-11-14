(function(window){'use strict';window.selfosUI.register('login',()=>{
let authMode='ready',generation=0;const requests=new Set(),cleanups=[];
function on(node,type,callback){node.addEventListener(type,callback);cleanups.push(()=>node.removeEventListener(type,callback));}
function language(value){window.selfosI18n.setLocale(value);document.getElementById('auth-language').value=window.selfosI18n.locale;}
function applyMode(data){
  if(data.authenticated){location.replace('/');return;}
  authMode=data.state;const setup=authMode==='setup';
  document.getElementById('auth-form').hidden=authMode==='locked';document.getElementById('auth-recovery').hidden=authMode!=='locked';
  document.getElementById('auth-heading').dataset.i18n=authMode==='locked'?'auth.locked':setup?'auth.setup':'auth.title';
  document.getElementById('auth-description').dataset.i18n=setup?'auth.setup_description':'auth.description';
  document.getElementById('auth-submit').dataset.i18n=setup?'auth.setup':'auth.login';
  document.getElementById('auth-confirm-row').hidden=!setup;document.getElementById('auth-confirm').required=setup;
  document.getElementById('auth-length').hidden=!setup;document.getElementById('auth-password').autocomplete=setup?'new-password':'current-password';window.selfosUI.module('auth').translate();

}
async function submit(e){
  e.preventDefault();const owner=generation,controller=new AbortController();requests.add(controller);const button=document.getElementById('auth-submit'),status=document.getElementById('auth-status'),password=document.getElementById('auth-password').value;
  if(authMode==='setup'&&password!==document.getElementById('auth-confirm').value){window.selfosUI.module('auth').status(status,'mismatch');requests.delete(controller);return;}
  button.disabled=true;window.selfosUI.module('auth').status(status,'working');
  try{await window.selfosUI.module('auth').request('/auth/'+(authMode==='setup'?'setup':'login'),{password},{signal:controller.signal});if(owner===generation)location.replace('/');}catch(error){if(owner!==generation)return;window.selfosUI.module('auth').status(status,error.code||'auth_error');document.getElementById('auth-password').value='';document.getElementById('auth-confirm').value='';}finally{requests.delete(controller);if(owner===generation)button.disabled=false;}

}
async function refresh(){const owner=generation,controller=new AbortController();requests.add(controller);try{const response=await fetch('/auth/status',{cache:'no-store',signal:controller.signal});if(!response.ok)throw Error('auth_status');const data=await response.json();if(owner===generation)applyMode(data);}catch(error){if(owner===generation)window.selfosUI.module('auth').status('auth-status','network');}finally{requests.delete(controller);}}
function init(){++generation;document.body.classList.toggle('auth-dark',localStorage.getItem('selfos-theme')==='dark');window.selfosI18n.populateLanguageSelect('auth-language');window.selfosUI.module('auth').translate();on(document.getElementById('auth-language'),'change',event=>language(event.target.value));on(document.getElementById('auth-form'),'submit',submit);refresh();}
function teardown(){++generation;for(const controller of requests)controller.abort();requests.clear();for(const id of ['auth-password','auth-confirm'])document.getElementById(id).value='';document.getElementById('auth-submit').disabled=false;cleanups.splice(0).reverse().forEach(cleanup=>cleanup());}
return {language,submit,refresh,init,teardown,busy:()=>requests.size>0};
},{dependencies:['auth','request','locale'],roots:['#auth-form','#auth-language']});
if(!window.authLanguage)window.authLanguage=(...args)=>window.selfosUI.module('login').language(...args);
})(window);
