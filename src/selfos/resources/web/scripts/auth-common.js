(function(window){'use strict';window.selfosUI.register('auth',()=>{
const authKey=key=>window.selfosI18n.has('auth.'+key)?key:'auth_error';
const authText=key=>window.selfosI18n.t('auth.'+authKey(key));
function translateAuth(){window.selfosI18n.translate();}
function authStatus(element,key){window.selfosI18n.bindText(element,'auth.'+authKey(key));}
async function authRequest(path,body,options={}){
 let response;
 try{response=await fetch(path,{signal:options.signal,method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});}catch(cause){const error=new Error(authText('network'));error.code='network';throw error;}
 let data;
 try{data=await response.json();}catch(cause){const error=new Error(authText('auth_error'));error.code='auth_error';error.status=response.status;throw error;}
 if(!response.ok){const code=authKey(data.error_code||'auth_error');const error=new Error(authText(code));error.code=code;error.status=response.status;throw error;}
 return data;
}
return {request:authRequest,status:authStatus,translate:translateAuth,key:authKey,text:authText};
},{dependencies:['request','locale']});
for(const [name,method]of Object.entries({authRequest:'request',authStatus:'status',translateAuth:'translate'}))if(!window[name])window[name]=(...args)=>window.selfosUI.module('auth')[method](...args);
})(window);
