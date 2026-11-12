async function updateKnowledgeOverview() {
 const i=window.selfosI18n,status=document.getElementById('knowledge-overview-status');
 try {
  const response=await fetch('/__knowledge_settings__');if(!response.ok)throw Error('knowledge_unavailable');
  const data=await response.json();
  for(const key of ['cards','lessons','personal_facts','preferences','history'])i.bindText('knowledge-count-'+key,'ui.common.value',{value:data.counts[key]||0});
  document.getElementById('knowledge-connection-dot').classList.add('ready');
  i.bindText(status,data.saved_checkpoints?'ui.overview.saved':'ui.overview.local',{count:data.saved_checkpoints||0});
 }catch(error){document.getElementById('knowledge-connection-dot').classList.remove('ready');i.bindText(status,'ui.overview.offline');}
}
document.addEventListener('DOMContentLoaded',updateKnowledgeOverview);
