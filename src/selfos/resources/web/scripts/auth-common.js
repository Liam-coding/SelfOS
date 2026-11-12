
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
