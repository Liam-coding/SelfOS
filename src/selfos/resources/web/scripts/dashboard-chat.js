(function(window){'use strict';window.selfosUI.register('chat',()=>{
let collapsed=null,generation=0,messageRoot=null,draft=null;
const history=[],requests=new Map(),cleanups=[];
const transcript=[];
const el=id=>document.getElementById(id);
function on(node,type,callback){node?.addEventListener?.(type,callback);cleanups.push(()=>node?.removeEventListener?.(type,callback));}
@@SELFOS_RESOURCE:scripts/knowledge-qa.js@@
const qa=createKnowledgeQA({el,on,requests});
function updateLabel(){const button=el('chat-collapse-btn');button.dataset.i18nAriaLabel=collapsed?'ui.chat.expand':'ui.chat.collapse';button.setAttribute('aria-label',window.selfosI18n.t(button.dataset.i18nAriaLabel));button.setAttribute('aria-expanded',String(!collapsed));}
function setOpen(open){collapsed=!open;el('chat-panel').classList.toggle('collapsed',collapsed);localStorage.setItem('selfos-chat-open',String(open));updateLabel();}
function toggle(event){event?.stopPropagation?.();setOpen(!!collapsed);}
function append(text,role,remember=true){const box=el('chat-messages'),node=document.createElement('div');node.className='msg '+(role==='user'?'msg-user':'msg-ai');node.dataset.selfosChatMessage='1';node.textContent=text;box.appendChild(node);box.scrollTop=box.scrollHeight;if(remember)transcript.push({role,content:text});return node;}
function cancel(){for(const [controller,thinking]of requests){controller.abort();thinking.remove();}requests.clear();el('chat-send').disabled=false;qa.update();}
async function ask(text,project=qa.project()){
 if(requests.size||!text.trim())return;const owner=generation,input=el('chat-input');input.value='';input.style.height='auto';append(text,'user');el('chat-send').disabled=true;
 const thinking=append('','ai',false);window.selfosI18n.bindText(thinking,'ui.chat.thinking');const controller=new AbortController();requests.set(controller,thinking);qa.update();
 try{const stopped=new Promise((_,reject)=>controller.signal.addEventListener('abort',()=>reject(Error('cancelled')),{once:true}));const response=await Promise.race([fetch('/__knowledge_qa__',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:text,project,locale:window.selfosI18n.locale}),signal:controller.signal}),stopped]);const data=await Promise.race([response.json(),stopped]);if(owner!==generation||controller.signal.aborted)return;if(!response.ok)throw Error(data.code||'qa_unavailable');thinking.remove();const holder=append('','ai',false);qa.render(holder,data);transcript.push({role:'assistant',data});}
 catch(error){if(owner===generation&&!controller.signal.aborted){thinking.classList.remove('thinking');window.selfosI18n.bindText(thinking,'qa.'+(error.message==='knowledge_changed'?'stale':'failed'));}}
 finally{requests.delete(controller);if(owner===generation){el('chat-send').disabled=!!requests.size;qa.update();input.focus();}}
}
async function send(text){
 const typed=text===undefined,input=el('chat-input');text=typed?input.value.trim():String(text);if(!text.trim())return;
 if(typed&&qa.mode()==='knowledge')return ask(text);
 const owner=generation;
 if(typed){input.value='';input.style.height='auto';el('chat-send').disabled=true;}
 append(text,'user');history.push({role:'user',content:text});
 const thinking=append('','ai',false);window.selfosI18n.bindText(thinking,'ui.chat.thinking');thinking.classList.add('thinking');
 const controller=new AbortController();requests.set(controller,thinking);
 try{const response=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:history}),signal:controller.signal});const data=await response.json();if(owner!==generation)return;if(!response.ok||typeof data.reply!=='string'||!data.reply.trim())throw Error('chat_failed');thinking.remove();append(data.reply,'ai');history.push({role:'assistant',content:data.reply});}
 catch(error){if(owner===generation)window.selfosI18n.bindText(thinking,'ui.chat.failed');}
 finally{requests.delete(controller);if(typed&&owner===generation){el('chat-send').disabled=false;input.focus();}}
}
function action(event){const node=event.target.closest?.('[data-selfos-action]');if(!node||!document.contains(node)||!node.closest('#chat-panel'))return;const actions={'chat.toggle':()=>toggle(event),'chat.send':()=>send(),'chat.cancel':cancel};if(!Object.hasOwn(actions,node.dataset.selfosAction))return;event.preventDefault();actions[node.dataset.selfosAction]();}
function init(){
 ++generation;if(collapsed===null)collapsed=localStorage.getItem('selfos-chat-open')!=='true';el('chat-panel').classList.toggle('collapsed',collapsed);updateLabel();
 const root=el('chat-messages');if(messageRoot){for(const node of root.querySelectorAll?.('[data-selfos-chat-message]')||[])node.remove();for(const item of transcript){const holder=append(item.content||'',item.role,false);if(item.data)qa.render(holder,item.data);}}messageRoot=root;
 if(draft){el('chat-input').value=draft.value;el('chat-input').style.height=draft.height;draft=null;}
 qa.init();
 on(document,'click',action);on(el('chat-input'),'keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();send();}});on(el('chat-input'),'input',function(){this.style.height='auto';this.style.height=Math.min(this.scrollHeight,80)+'px';});on(document,'selfos-language',updateLabel);
}
function teardown(){draft={value:el('chat-input').value,height:el('chat-input').style.height};++generation;qa.teardown();cancel();cleanups.splice(0).reverse().forEach(cleanup=>cleanup());}
return {open:()=>setOpen(true),toggle,send,ask,cancel,setMode:qa.setMode,append,snapshot:()=>Object.freeze({collapsed,history:Object.freeze(history.map(item=>Object.freeze({...item}))),pending:requests.size}),init,teardown,busy:()=>requests.size>0,updateLabel};
},{dependencies:['request','locale'],roots:['#chat-panel']});
for(const [name,method]of Object.entries({toggleChat:'toggle',appendMsg:'append',sendChat:'send',_sendChatSilent:'send',updateChatLabel:'updateLabel'}))if(!window[name])window[name]=(...args)=>window.selfosUI.module('chat')[method](...args);
})(window);
