(() => {
  if(window.selfosUploads)return;
  const state={documents:new Map(),selected:new Set(),queue:[],busy:false,organizing:false,cancelled:false,xhr:null,
    preview:null,previewGeneration:0,listGeneration:0,sourceGeneration:0,offset:0,total:0,model:null,status:null,source:null,returnFocus:null};
  const el=id=>document.getElementById('uploads-'+id);
  const t=(key,params={})=>window.selfosI18n.t('upload.'+key,params);
  const bind=(id,key,params={})=>window.selfosI18n.bindText(el(id),'upload.'+key,params);
  const textNode=(tag,text)=>{const node=document.createElement(tag);node.textContent=text;return node;};
  const status=(key,params={})=>{state.status={key,params};bind('status',key,params);};
  function select(identity){
    if(state.selected.has(identity))return true;
    if(state.selected.size>=10){status('selection_limit');return false;}
    state.selected.add(identity);return true;
  }
  async function request(url,body){
    const response=await fetch(url,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await response.json();if(!response.ok){const error=new Error(data.code||'unavailable');error.code=response.status===401?'login_required':response.status===409?'import_active':'unavailable';throw error;}return data;
  }
  function invalidate(){state.preview=null;++state.previewGeneration;el('preview-summary').textContent='';render();}
  function render(){
    if(!el('dialog'))return;
    el('queue').replaceChildren();
    for(const item of state.queue){const row=document.createElement('div');row.className='uploads-queue-row';row.dataset.uploadStatus=item.status;
      const content=document.createElement('div');content.append(textNode('strong',item.name),textNode('small',t(item.status)));
      if(item.status==='uploading'){const progress=document.createElement('progress');progress.max=item.size;progress.value=item.loaded;progress.setAttribute('aria-label',t('uploading'));content.append(progress);}row.append(content);el('queue').append(row);}
    el('list').replaceChildren();
    for(const doc of state.documents.values()){const row=document.createElement('div');row.className='uploads-row';const label=document.createElement('label'),checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.checked=state.selected.has(doc.id);checkbox.disabled=doc.status==='original_or_index_unavailable'||doc.status==='excluded';
      checkbox.addEventListener('change',()=>{if(checkbox.checked)select(doc.id);else state.selected.delete(doc.id);invalidate();});
      const names=document.createElement('span');names.append(textNode('strong',doc.original_filename),textNode('small',t('document_status',{status:t(doc.status||'uploaded'),count:doc.processed_parts||0})));label.append(checkbox,names);
      const view=textNode('button',t('view'));view.type='button';view.dataset.uploadView=doc.id;view.addEventListener('click',()=>viewSource(doc.id));row.append(label,view);el('list').append(row);}
    if(!state.documents.size)el('list').append(textNode('p',t('empty')));
    bind('selection','selected',{count:state.selected.size});
    el('choose').disabled=state.busy;el('files').disabled=state.busy;el('cancel').hidden=!state.xhr&&!state.queue.some(item=>item.status==='queued');
    el('preview').disabled=state.busy||state.organizing||!state.selected.size;el('organize').disabled=state.busy||state.organizing||!state.preview?.sessions.length;
    el('more').hidden=state.offset>=state.total;el('more').disabled=state.busy;
    if(state.status)bind('status',state.status.key,state.status.params);
    if(state.model)bind('model','model',{provider:state.model.provider,model:state.model.model||t('default_model')});
    if(state.preview)bind('preview-summary',state.preview.sessions.length?'preview_summary':'cached_summary',{
      parts:state.preview.sessions.length,cached:state.preview.cached_parts,limit:state.preview.budget_limit,
      coverage:t(state.preview.partial_coverage?'partial':'complete')});
    if(state.source){el('source-text').textContent=state.source.text;el('source-more').hidden=state.source.next===null;}
  }
  async function loadDocuments(more=false){
    const generation=++state.listGeneration;
    try{const page=await request('/__knowledge_uploads__?'+new URLSearchParams({offset:more?state.offset:0,limit:50}));
      if(generation!==state.listGeneration)return;if(!more)state.documents.clear();for(const doc of page.items)state.documents.set(doc.id,doc);state.offset=(more?state.offset:0)+page.items.length;state.total=page.total;render();
    }catch(error){if(generation===state.listGeneration)status(error.code||'unavailable');}
  }
  async function open(){
    state.returnFocus=document.activeElement;if(!el('dialog').open)el('dialog').showModal();render();
    await loadDocuments();try{state.model=await request('/__model_settings__');render();}catch(error){status(error.code||'unavailable');}
  }
  function transfer(item){
    return new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();state.xhr=xhr;
      xhr.open('POST','/__knowledge_upload__');xhr.timeout=35000;xhr.setRequestHeader('Content-Type','application/octet-stream');xhr.setRequestHeader('X-SelfOS-Filename',encodeURIComponent(item.name));
      xhr.upload.onprogress=event=>{item.loaded=event.loaded;render();};
      xhr.onload=()=>{let data;try{data=JSON.parse(xhr.responseText);}catch(error){reject(new Error('unavailable'));return;}
        if(xhr.status===200||xhr.status===201)resolve(data);else reject(new Error(xhr.status===401?'login_required':xhr.status===408?'interrupted':'rejected'));};
      xhr.onerror=()=>reject(new Error('unavailable'));xhr.ontimeout=()=>reject(new Error('interrupted'));xhr.onabort=()=>reject(new Error('interrupted'));xhr.send(item.file);
    });
  }
  async function enqueue(files){
    if(state.busy)return;const chosen=Array.from(files);if(chosen.length>10){status('too_many');return;}if(!chosen.length)return;
    ++state.listGeneration;invalidate();state.cancelled=false;state.busy=true;let selectionLimited=false;state.queue=chosen.map(file=>({file,name:file.name,size:file.size,loaded:0,status:'queued'}));render();
    for(const item of state.queue){
      if(state.cancelled){item.status='interrupted';item.file=null;continue;}
      if(!/\.(txt|md)$/i.test(item.name)||item.size===0||item.size>20*1024*1024){item.status='rejected';item.file=null;render();continue;}
      item.status='uploading';render();
      try{const result=await transfer(item);item.status=result.duplicate?'duplicate':'uploaded';
        const previous=state.documents.get(result.document.id);state.documents.set(result.document.id,{status:'uploaded',processed_parts:0,...previous,...result.document});if(!select(result.document.id))selectionLimited=true;
      }catch(error){item.status=error.message;if(error.message==='login_required'){state.cancelled=true;status('login_required');}}
      finally{state.xhr=null;item.file=null;render();}
    }
    state.busy=false;el('files').value='';render();if(!state.cancelled)status(selectionLimited?'selection_limit':'local_saved');await loadDocuments();
  }
  function cancel(){state.cancelled=true;state.xhr?.abort();status('interrupted');}
  async function prepare(){
    if(state.busy||state.organizing||!state.selected.size)return;const generation=++state.previewGeneration;state.busy=true;render();status('preparing');
    try{const preview=await request('/__knowledge_upload_preview__',{ids:Array.from(state.selected)});if(generation===state.previewGeneration){state.preview=preview;status('prepared');}}
    catch(error){if(generation===state.previewGeneration)status(error.code||'unavailable');}
    finally{state.busy=false;render();}
  }
  function organize(){
    if(state.busy||state.organizing||!state.preview?.sessions.length)return;const id=state.preview.id;
    el('dialog').close();confirmHarvest(false,true,false,'/__knowledge_stream__?upload_preview='+encodeURIComponent(id));
  }
  async function viewSource(id,more=false){
    const generation=++state.sourceGeneration;const current=more?state.source:null;
    if(!more)state.source={id,text:'',next:0};el('source').hidden=false;
    try{const data=await request('/__knowledge_upload_source__?'+new URLSearchParams({id,offset:current?.next||0,limit:24000}));
      if(generation!==state.sourceGeneration)return;state.source={id,text:(current?.text||'')+data.text,next:data.next_offset??null};render();
    }catch(error){if(generation===state.sourceGeneration)status(error.code||'unavailable');}
  }
  function init(){
    el('open').addEventListener('click',open);el('close').addEventListener('click',()=>el('dialog').close());
    el('dialog').addEventListener('close',()=>{++state.sourceGeneration;state.returnFocus?.focus();});
    el('choose').addEventListener('click',()=>el('files').click());el('files').addEventListener('change',event=>enqueue(event.target.files));
    el('cancel').addEventListener('click',cancel);el('preview').addEventListener('click',prepare);el('organize').addEventListener('click',organize);
    el('more').addEventListener('click',()=>loadDocuments(true));el('source-close').addEventListener('click',()=>{++state.sourceGeneration;el('source').hidden=true;state.source=null;});el('source-more').addEventListener('click',()=>viewSource(state.source.id,true));
    const drop=el('drop');drop.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();if(!state.busy)el('files').click();}});
    for(const name of ['dragenter','dragover'])drop.addEventListener(name,event=>{event.preventDefault();drop.dataset.dragging='true';});
    drop.addEventListener('dragleave',()=>drop.dataset.dragging='false');drop.addEventListener('drop',event=>{event.preventDefault();drop.dataset.dragging='false';enqueue(event.dataTransfer.files);});
    document.addEventListener('selfos-language',render);document.addEventListener('selfos-import-started',()=>{state.organizing=true;render();});
    document.addEventListener('selfos-import-finished',()=>{state.organizing=false;invalidate();loadDocuments();});render();
  }
  window.selfosUploads={open,refresh:loadDocuments};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
