(function(window){
  'use strict';
  window.selfosUI.register('account',()=>{
    let document=null,generation=0;
    const requests=new Set();
    async function request(path,body){const controller=new AbortController();requests.add(controller);try{return await authRequest(path,body,{signal:controller.signal});}finally{requests.delete(controller);}}
    function openChange(){document.getElementById('app-settings').close();document.getElementById('auth-change').showModal();}
    function closeChange(){document.getElementById('auth-change').close();document.querySelectorAll('#auth-change input').forEach(input=>input.value='');}
    async function logout(){
      const current=generation;
      try{await request('/auth/logout',{});if(current===generation)location.replace('/login');}
      catch(error){if(current!==generation)return;if(error.status===401)location.replace('/login');else authStatus('auth-account-status',error.code||'auth_error');}
    }
    async function changePassword(event){
      event.preventDefault();
      const doc=document,current=generation,status=doc.getElementById('auth-change-status'),password=doc.getElementById('auth-new').value;
      if(password!==doc.getElementById('auth-new-confirm').value){authStatus(status,'mismatch');return;}
      const button=event.target.querySelector('button[type=submit]');button.disabled=true;
      try{await request('/auth/change',{current_password:doc.getElementById('auth-current').value,password});if(current===generation)location.replace('/login');}
      catch(error){if(current!==generation)return;authStatus(status,error.code||'auth_error');doc.querySelectorAll('#auth-change input').forEach(input=>input.value='');}
      finally{if(current===generation)button.disabled=false;}
    }
    function action(event){
      const node=event.target.closest?.('[data-selfos-action]');
      if(!node||!document.contains(node)||!node.closest('#auth-account-buttons,#auth-change'))return;
      const actions={'account.change':['click',openChange],'account.logout':['click',logout],'account.close':['click',closeChange],'account.save':['submit',changePassword]};
      const entry=actions[node.dataset.selfosAction];
      if(!entry||entry[0]!==event.type)return;
      event.preventDefault();entry[1](event);
    }
    return {request,logout,openChange,changePassword,busy:()=>requests.size>0,
      init(doc){
        document=doc;++generation;
        const account=doc.getElementById('settings-account'),buttons=doc.getElementById('auth-account-buttons');
        if(account&&buttons){account.append(buttons);account.hidden=false;}
        doc.addEventListener('click',action);doc.addEventListener('submit',action);translateAuth();
      },
      teardown(){++generation;for(const controller of requests)controller.abort();requests.clear();document.removeEventListener('click',action);document.removeEventListener('submit',action);document.querySelectorAll?.('#auth-change input').forEach(input=>input.value='');document=null;}
    };
  },{dependencies:['request','locale'],roots:['#auth-account-buttons','#auth-change','#settings-account']});
  for(const [name,method]of Object.entries({logoutSelfOS:'logout',changeSelfOSPassword:'changePassword'}))if(!window[name])window[name]=(...args)=>window.selfosUI.module('account')[method](...args);
})(window);
