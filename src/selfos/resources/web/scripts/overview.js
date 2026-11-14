(function(window){'use strict';window.selfosUI.register('overview',()=>{
let generation=0,fetching=false,queued=false,unsubscribe=null;const requests=new Set();
async function updateKnowledgeOverview() {
 if(fetching){queued=true;return;}fetching=true;const current=generation,controller=new AbortController();requests.add(controller);
 const i=window.selfosI18n,status=document.getElementById('knowledge-overview-status');
 try {
  const response=await fetch('/__knowledge_settings__',{cache:'no-store',signal:controller.signal});if(!response.ok)throw Error('knowledge_unavailable');
  const data=await response.json();if(current!==generation)return;
  for(const key of ['cards','lessons','personal_facts','preferences','history'])i.bindText('knowledge-count-'+key,'ui.common.value',{value:data.counts[key]||0});
  document.getElementById('knowledge-connection-dot').classList.add('ready');
  i.bindText(status,data.saved_checkpoints?'ui.overview.saved':'ui.overview.local',{count:data.saved_checkpoints||0});
 }catch(error){if(current!==generation)return;document.getElementById('knowledge-connection-dot').classList.remove('ready');i.bindText(status,'ui.overview.offline');}finally{requests.delete(controller);if(current===generation){fetching=false;if(queued){queued=false;updateKnowledgeOverview();}}}
}
function action(event){const button=event.target.closest?.('[data-selfos-action]');if(!button||!document.contains(button)||!button.closest('.knowledge-overview'))return;const actions={'overview.browse':()=>window.selfosUI.module('knowledge').browse('projects'),'overview.build':()=>window.selfosUI.module('jobs').start(false,true),'overview.settings':()=>window.selfosUI.module('import-settings').open()};if(!Object.hasOwn(actions,button.dataset.selfosAction))return;event.preventDefault();actions[button.dataset.selfosAction]();}
function init(){++generation;document.addEventListener('click',action);unsubscribe=window.selfosUI.module('jobs').subscribe(state=>{if(state.kind==='knowledge'&&state.event==='finished')updateKnowledgeOverview();});updateKnowledgeOverview();}
function teardown(){++generation;document.removeEventListener('click',action);for(const controller of requests)controller.abort();requests.clear();fetching=false;queued=false;unsubscribe?.();unsubscribe=null;}
return {refresh:updateKnowledgeOverview,init,teardown,busy:()=>requests.size>0};
},{dependencies:['jobs','knowledge','import-settings','request','locale'],roots:['.knowledge-overview']});
if(!window.updateKnowledgeOverview)window.updateKnowledgeOverview=(...args)=>window.selfosUI.module('overview').refresh(...args);
})(window);
