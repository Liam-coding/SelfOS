(function(window){'use strict';window.selfosUI.register('chat',()=>{
let collapsed=null,generation=0,messageRoot=null,draft=null;
const history=[],requests=new Map(),cleanups=[];
const el=id=>document.getElementById(id);
function on(node,type,callback){node?.addEventListener?.(type,callback);cleanups.push(()=>node?.removeEventListener?.(type,callback));}
function updateLabel(){const button=el('chat-collapse-btn');button.dataset.i18nAriaLabel=collapsed?'ui.chat.expand':'ui.chat.collapse';button.setAttribute('aria-label',window.selfosI18n.t(button.dataset.i18nAriaLabel));button.setAttribute('aria-expanded',String(!collapsed));}
function setOpen(open){collapsed=!open;el('chat-panel').classList.toggle('collapsed',collapsed);localStorage.setItem('selfos-chat-open',String(open));updateLabel();}
function toggle(event){event?.stopPropagation?.();setOpen(!!collapsed);}
function append(text,role){const box=el('chat-messages'),node=document.createElement('div');node.className='msg '+(role==='user'?'msg-user':'msg-ai');node.dataset.selfosChatMessage='1';node.textContent=text;box.appendChild(node);box.scrollTop=box.scrollHeight;return node;}
async function send(text){
 const typed=text===undefined,input=el('chat-input');text=typed?input.value.trim():String(text);if(!text.trim())return;
 const owner=generation;
 if(typed){input.value='';input.style.height='auto';el('chat-send').disabled=true;}
 append(text,'user');history.push({role:'user',content:text});
 const thinking=append('','ai');window.selfosI18n.bindText(thinking,'ui.chat.thinking');thinking.classList.add('thinking');
 const controller=new AbortController();requests.set(controller,thinking);
 try{const response=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:history}),signal:controller.signal});const data=await response.json();if(owner!==generation)return;if(!response.ok||typeof data.reply!=='string'||!data.reply.trim())throw Error('chat_failed');thinking.remove();append(data.reply,'ai');history.push({role:'assistant',content:data.reply});}
 catch(error){if(owner===generation)window.selfosI18n.bindText(thinking,'ui.chat.failed');}
 finally{requests.delete(controller);if(typed&&owner===generation){el('chat-send').disabled=false;input.focus();}}
}
function action(event){const node=event.target.closest?.('[data-selfos-action]');if(!node||!document.contains(node)||!node.closest('#chat-panel'))return;const actions={'chat.toggle':()=>toggle(event),'chat.send':()=>send()};if(!Object.hasOwn(actions,node.dataset.selfosAction))return;event.preventDefault();actions[node.dataset.selfosAction]();}
function init(){
 ++generation;if(collapsed===null)collapsed=localStorage.getItem('selfos-chat-open')!=='true';el('chat-panel').classList.toggle('collapsed',collapsed);updateLabel();
 const root=el('chat-messages');if(messageRoot&&messageRoot!==root){for(const node of root.querySelectorAll?.('[data-selfos-chat-message]')||[])node.remove();for(const item of history)append(item.content,item.role);}messageRoot=root;
 if(draft){el('chat-input').value=draft.value;el('chat-input').style.height=draft.height;draft=null;}
 on(document,'click',action);on(el('chat-input'),'keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();send();}});on(el('chat-input'),'input',function(){this.style.height='auto';this.style.height=Math.min(this.scrollHeight,80)+'px';});on(document,'selfos-language',updateLabel);
}
function teardown(){draft={value:el('chat-input').value,height:el('chat-input').style.height};++generation;for(const [controller,thinking]of requests){controller.abort();thinking.remove();}requests.clear();el('chat-send').disabled=false;cleanups.splice(0).reverse().forEach(cleanup=>cleanup());}
return {open:()=>setOpen(true),toggle,send,append,snapshot:()=>Object.freeze({collapsed,history:Object.freeze(history.map(item=>Object.freeze({...item}))),pending:requests.size}),init,teardown,busy:()=>requests.size>0,updateLabel};
},{dependencies:['request','locale'],roots:['#chat-panel']});
for(const [name,method]of Object.entries({toggleChat:'toggle',appendMsg:'append',sendChat:'send',_sendChatSilent:'send',updateChatLabel:'updateLabel'}))if(!window[name])window[name]=(...args)=>window.selfosUI.module('chat')[method](...args);
})(window);
