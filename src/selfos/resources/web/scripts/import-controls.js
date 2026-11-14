(function(window){
  'use strict';
  window.selfosUI.register('import-settings',()=>{
    let knowledgeOperation=null,generation=0,dirty=false,loading=false,pendingRefresh=false,remountDraft=null;
    const requests=new Set(),cleanups=[];
    const domains={work:'ui.import_settings.work',research:'ui.import_settings.research',learning:'ui.import_settings.learning',personal:'ui.import_settings.personal_facts_and_preferences',life:'ui.import_settings.life',health:'ui.import_settings.health'};
    const el=id=>document.getElementById(id),status=key=>window.selfosI18n.bindText('knowledge-status',key);
    function on(node,type,callback){node?.addEventListener?.(type,callback);cleanups.push(()=>node?.removeEventListener?.(type,callback));}
    async function request(url,body){const controller=new AbortController();requests.add(controller);try{const response=await fetch(url,{signal:controller.signal,...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});const data=await response.json();if(!response.ok)throw Error('knowledge_settings_failed');return data;}finally{requests.delete(controller);}}
    function display(data){
      if(data.usage)window.selfosUI.module('usage').render(data.usage);
      window.selfosUI.module('publication').render(data);
      knowledgeOperation=data.last_operation?data.last_operation.id:null;el('knowledge-undo').disabled=!knowledgeOperation;
      status(data.needs_rebuild?'ui.import_settings.settings_changed_the_next_import_will_rebuild_automatically':'ui.import_settings.settings_saved');
    }
    function controls(disabled){el('knowledge-settings').querySelectorAll('input,select,button').forEach(control=>{if(control.dataset.selfosAction!=='import.close')control.disabled=disabled;});if(!disabled)el('knowledge-undo').disabled=!knowledgeOperation;}
    function renderDomains(selected){const container=el('knowledge-domains');container.replaceChildren();for(const [key,title]of Object.entries(domains)){const label=document.createElement('label');label.style.marginRight='12px';const input=document.createElement('input');input.type='checkbox';input.value=key;input.checked=selected.includes(key);const span=document.createElement('span');span.dataset.domain=key;window.selfosI18n.bindText(span,title);label.append(input,span);container.append(label);}}
    function fill(data){
      renderDomains(data.settings.domains);
      el('knowledge-custom').value=data.settings.domains.filter(domain=>!(domain in domains)).join(', ');el('knowledge-detail').value=data.settings.detail;
      if(data.usage)window.selfosUI.module('usage').render(data.usage,true);display(data);dirty=false;
    }
    async function load(){
      const dialog=el('knowledge-settings'),current=++generation;loading=true;controls(true);status('ui.import_settings.loading_settings');
      try{const data=await request('/__knowledge_settings__');if(current!==generation||!dialog.open)return;fill(data);}
      catch(error){if(current===generation)status('ui.import_settings.request_failed');}
      finally{if(current===generation){loading=false;controls(false);}}
    }
    async function open(){const dialog=el('knowledge-settings');if(dialog.open)return;dialog.showModal();await load();}
    function close(){el('knowledge-settings').close();}
    async function save(rebuild=false){
      if(window.selfosReadOnlyDemo)return;
      const current=generation;
      const selected=[...document.querySelectorAll('#knowledge-domains input:checked')].map(input=>input.value);
      selected.push(...el('knowledge-custom').value.split(/[,，]/).map(value=>value.trim()).filter(Boolean));
      try{const data=await request('/__knowledge_settings__',{domains:[...new Set(selected)],detail:el('knowledge-detail').value});if(current!==generation)return;display(data);dirty=false;if(rebuild){close();window.selfosUI.module('jobs').start(false,true,true);}}
      catch(error){if(current===generation)status('ui.import_settings.request_failed');}
    }
    async function restore(){
      if(!knowledgeOperation||window.selfosReadOnlyDemo)return;
      const current=generation,button=el('knowledge-undo');button.disabled=true;
      try{const data=await request('/__knowledge_restore__',{operation_id:knowledgeOperation});if(current!==generation)return;display(data);status('ui.import_settings.last_import_undone_backups_are_retained');}
      catch(error){if(current===generation){status('ui.import_settings.request_failed');button.disabled=!knowledgeOperation;}}
    }
    async function refreshStatus(){
      if(el('knowledge-settings').open&&dirty){pendingRefresh=true;return;}
      const current=generation;
      try{const data=await request('/__knowledge_settings__');if(current===generation)display(data);}catch(error){if(current===generation)status('ui.import_settings.request_failed');}
    }
    function action(event){
      const node=event.target.closest?.('[data-selfos-action]');if(!node||!document.contains(node)||!node.closest('#knowledge-settings,#knowledge-settings-entry'))return;
      const actions={'import.open':open,'import.save':()=>save(false),'import.rebuild':()=>save(true),'import.restore':restore,'import.close':close};if(!Object.hasOwn(actions,node.dataset.selfosAction))return;event.preventDefault();actions[node.dataset.selfosAction]();
    }
    function init(){
      ++generation;on(document,'click',action);on(el('knowledge-settings'),'input',()=>{dirty=true;});on(el('knowledge-settings'),'change',()=>{dirty=true;});
      on(el('knowledge-settings'),'close',()=>{++generation;if(pendingRefresh){pendingRefresh=false;refreshStatus();}});
      cleanups.push(window.selfosUI.module('jobs').subscribe(state=>{if(state.kind==='knowledge'&&state.event==='finished')refreshStatus();}));
      const header=document.querySelector('.header-btns');if(header)header.append(el('knowledge-settings-entry'));
      if(remountDraft){el('knowledge-custom').value=remountDraft.custom;el('knowledge-detail').value=remountDraft.detail;el('workload-limit').value=remountDraft.limit;renderDomains(remountDraft.domains);dirty=remountDraft.dirty;if(remountDraft.open){const dialog=el('knowledge-settings');if(dialog.open)dialog.close();dialog.showModal();}const resumeLoading=remountDraft.loading&&remountDraft.open;remountDraft=null;if(resumeLoading)load();else controls(false);}
    }
    function teardown(){
      remountDraft={custom:el('knowledge-custom').value,detail:el('knowledge-detail').value,limit:el('workload-limit').value,domains:[...el('knowledge-domains').querySelectorAll('input:checked')].map(input=>input.value),open:el('knowledge-settings').open,dirty,loading};
      ++generation;loading=false;for(const controller of requests)controller.abort();requests.clear();cleanups.splice(0).reverse().forEach(cleanup=>cleanup());
    }
    return {open,close,save,restore,display,request,status,refresh:refreshStatus,busy:()=>requests.size>0,init,teardown};
  },{dependencies:['jobs','usage','publication','request','locale'],roots:['#knowledge-settings','#knowledge-settings-entry']});
  for(const [name,method]of Object.entries({openKnowledgeSettings:'open',saveKnowledgeSettings:'save',undoKnowledge:'restore',displayKnowledgeStatus:'display',knowledgeRequest:'request',setKnowledgeStatus:'status'}))if(!window[name])window[name]=(...args)=>window.selfosUI.module('import-settings')[method](...args);
})(window);
