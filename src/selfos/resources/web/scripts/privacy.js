let privacySelection=null;
let privacyPreparedExport=null;
function privacyMessage(key){return window.selfosI18n?window.selfosI18n.t('privacy.'+key):key;}
async function privacyRequest(body){
  const response=await fetch('/__privacy__',body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});
  const data=await response.json();
  if(!response.ok)throw new Error(privacyMessage('error'));
  return data;
}
async function openPrivacySettings(){
  document.getElementById('app-settings').close();
  document.getElementById('privacy-settings').showModal();
  try{const data=await privacyRequest();privacySelection=data.selection;
    document.getElementById('privacy-rules').value=[...privacySelection.exclusions,...(privacySelection.privacy_exclusions||[])].join(String.fromCharCode(10));
    document.getElementById('privacy-destination').textContent=Object.values(data.destination).join(String.fromCharCode(10));
    document.getElementById('privacy-status').textContent=privacyMessage('withheld')+' '+data.withheld_sources;
  }catch(error){document.getElementById('privacy-status').textContent=error.message;}
}
async function savePrivacyRules(){
  try{if(!privacySelection)throw new Error(privacyMessage('error'));
    const rules=document.getElementById('privacy-rules').value.split(String.fromCharCode(10)).map(s=>s.trim()).filter(Boolean);
    await privacyRequest({action:'save',selection:{...privacySelection,exclusions:[],privacy_exclusions:rules}});
    document.getElementById('privacy-status').textContent=privacyMessage('saved');
  }catch(error){document.getElementById('privacy-status').textContent=error.message;}
}
async function exportPrivacyData(){
  document.getElementById('privacy-download').hidden=true;privacyPreparedExport=null;
  try{const data=await privacyRequest({action:'export',originals:document.getElementById('privacy-originals').checked,backups:document.getElementById('privacy-backups').checked,audit:document.getElementById('privacy-audit').value,audit_recent:Number(document.getElementById('privacy-audit-recent').value)});
    privacyPreparedExport=JSON.stringify(data,null,2);
    const summary=data.audit_summary;window.selfosI18n.bindText(document.getElementById('privacy-status'),'ui.common.value',()=>({value:window.selfosI18n.t('changes.export_summary',{operations:summary.operations,bytes:summary.bytes})+' '+(summary.oldest?window.selfosI18n.t('changes.export_range',{oldest:summary.oldest.run_id+':'+summary.oldest.index,newest:summary.newest.run_id+':'+summary.newest.index})+' ':'')+window.selfosI18n.t('changes.'+(summary.earlier_history_omitted?'omitted':'complete'))}));
    document.getElementById('privacy-download').hidden=false;
  }catch(error){document.getElementById('privacy-status').textContent=error.message;}
}
function downloadPrivacyData(){
    if(!privacyPreparedExport)return;
    const url=URL.createObjectURL(new Blob([privacyPreparedExport],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='selfos-portable.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    document.getElementById('privacy-status').textContent=privacyMessage('exported');
}
async function importPrivacyData(file){
  if(!file)return;
  try{if(file.size>90*1024*1024)throw new Error(privacyMessage('error'));
    const data=await privacyRequest({action:'import',package:JSON.parse(await file.text())});
    document.getElementById('privacy-status').textContent=privacyMessage('imported')+String.fromCharCode(10)+JSON.stringify(data.sources,null,2);
  }catch(error){document.getElementById('privacy-status').textContent=error.message;}
}
