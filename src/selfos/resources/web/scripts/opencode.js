(() => {
  if(window.selfosHarness)return;
  const state={selection:null,available:[],checked:new Set(),extra:new Set(),preview:null,entry:null,busy:false,generation:0,status:'ready'};
  const el=id=>document.getElementById('native-'+id),t=(key,params={})=>window.selfosI18n.t('native.'+key,params);
  const node=(tag,value)=>{const item=document.createElement(tag);item.textContent=value;return item;};
  const changed=()=>{onboardingSourcesDirty=true;};
  function renderSources(){
    if(!el('entries'))return;el('entries').replaceChildren();
    const paths=new Map(state.available.filter(item=>item.kind==='opencode_database'&&typeof item.path==='string').map(item=>[item.path,item.available]));
    for(const entry of state.selection?.entries||[])if(entry.kind==='opencode_database')paths.set(entry.path,paths.get(entry.path)??true);
    for(const path of state.extra)paths.set(path,true);
    for(const [path,available] of paths){
      const row=document.createElement('div');row.className='native-row';const label=document.createElement('label'),input=document.createElement('input');
      input.type='checkbox';input.checked=state.checked.has(path);input.dataset.nativePath=path;
      input.addEventListener('change',()=>{if(input.checked)state.checked.add(path);else state.checked.delete(path);changed();});
      label.append(input,node('span',path));row.append(label,node('small',t(available?'available':'missing')));
      const button=node('button',t('preview'));button.type='button';button.dataset.nativePreview=path;
      button.disabled=state.busy||!state.selection?.entries?.some(item=>item.kind==='opencode_database'&&item.path===path);
      button.addEventListener('click',()=>{if(state.preview&&state.entry?.path===path){if(!el('dialog').open)el('dialog').showModal();renderPreview();}
        else prepare({kind:'opencode_database',path});});row.append(button);el('entries').append(row);
    }
    el('source-status').textContent=t('save_help');
  }
  function renderPreview(){
    el('status').textContent=t(state.status,{parts:state.preview?.sessions.length||0});
    el('start').disabled=state.busy||!state.preview?.sessions.length;
    el('more').disabled=state.busy||!state.entry;
    el('reset').disabled=state.busy||!state.entry;
    el('excerpts').replaceChildren();
    for(const session of state.preview?.sessions||[]){const article=document.createElement('article');article.append(node('strong',session.project_id));
      for(const message of session.messages)article.append(node('pre',message.role+' · '+message.timestamp+'\n'+message.text));el('excerpts').append(article);}
  }
  async function prepare(entry,restart=false){
    if(state.busy)return;state.entry=entry;state.preview=null;state.busy=true;state.status='scanning';const generation=++state.generation;
    if(!el('dialog').open)el('dialog').showModal();renderPreview();renderSources();
    try{const response=await fetch('/__knowledge_native_preview__',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({entry,restart})});
      const data=await response.json();if(generation!==state.generation)return;
      if(!response.ok)throw new Error(response.status===401?'login_required':response.status===409?'import_active':'unavailable');
      state.preview=data;state.status=data.sessions.length?'prepared':window.selfosI18n.has('native.'+data.status)?data.status:'unavailable';
    }catch(error){if(generation===state.generation)state.status=error.message;}
    finally{if(generation===state.generation){state.busy=false;renderPreview();renderSources();}}
  }
  function update(selection,availability,dirty){
    if(state.selection&&JSON.stringify(state.selection)!==JSON.stringify(selection))state.preview=null;
    state.selection=selection;state.available=availability;
    if(!dirty){state.checked=new Set((selection.entries||[]).filter(item=>item.kind==='opencode_database').map(item=>item.path));state.extra.clear();
      document.getElementById('onboarding-project-exclusions').value=(selection.project_exclusions||[]).join('\n');}
    renderSources();
  }
  function init(){
    document.getElementById('onboarding-save-sources').before(el('controls'));el('controls').hidden=false;
    el('add').addEventListener('click',()=>{const path=el('path').value.trim();if(!path)return;state.extra.add(path);state.checked.add(path);el('path').value='';changed();renderSources();});
    document.getElementById('onboarding-project-exclusions').addEventListener('input',changed);
    el('close').addEventListener('click',()=>el('dialog').close());
    el('dialog').addEventListener('close',()=>{++state.generation;state.busy=false;});
    el('more').addEventListener('click',()=>prepare(state.entry));
    el('reset').addEventListener('click',()=>prepare(state.entry,true));
    el('start').addEventListener('click',()=>{if(!state.preview?.sessions.length)return;const url='/__knowledge_stream__?native_preview='+state.preview.id;
      el('dialog').close();document.getElementById('onboarding-dialog').close();confirmHarvest(false,true,false,url);});
    document.addEventListener('selfos-language',()=>{renderSources();renderPreview();});
  }
  window.selfosHarness={update,entries:()=>[...state.checked].map(path=>({kind:'opencode_database',path}))};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
