(function(){
  const el=id=>document.getElementById(id);
  const tr=key=>window.selfosI18n.t('workload.'+key);
  const num=value=>window.selfosI18n.number(value);
  const bind=(id,key,values={})=>window.selfosI18n.bindText(id,'workload.'+key,values);
  let generation=0;
  function busy(value){el('workload-preview').disabled=value;el('workload-save').disabled=value;}
  async function request(url,body){
    const response=await fetch(url,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await response.json();
    if(!response.ok){const error=new Error('workload_request_failed');error.code=data.code;throw error;}
    return data;
  }
  function errorStatus(error){bind('workload-status',error.code==='budget_import_active'?'active':error.code==='budget_invalid'?'invalid':'failed');}
  window.renderWorkloadUsage=function(data,populate=false){
    if(!data||!el('workload-controls'))return;
    if(populate){
      el('workload-limit').value=data.budget.max_requests;
      el('workload-input-price').value=data.budget.input_price??'';
      el('workload-output-price').value=data.budget.output_price??'';
    }
    const run=data.runs?.[0];
    if(!run){bind('workload-usage','empty_usage');return;}
    bind('workload-usage','usage',()=>({used:num(run.used),limit:num(run.limit),
      input:num(run.input_tokens),output:num(run.output_tokens),seconds:num(Math.round(run.elapsed_seconds)),
      missing:num(run.missing_usage),cost:run.cost_usd==null?tr('cost_unknown'):tr('usd')+' '+num(run.cost_usd)}));
  };
  window.loadWorkloadPreview=async function(){
    const current=++generation;busy(true);bind('workload-status','loading');
    try{
      const data=await request('/__knowledge_workload__');
      if(current!==generation||!el('knowledge-settings').open)return;
      bind('workload-preview-result','estimate',()=>({files:num(data.files_scanned),messages:num(data.messages_scanned),
        pending:num(data.pending_parts),cached:num(data.cached_parts),
        calls:num(data.estimate.calls.low)+'–'+num(data.estimate.calls.high),
        input:num(data.estimate.input_tokens.low)+'–'+num(data.estimate.input_tokens.high),
        output:num(data.estimate.output_tokens.low)+'–'+num(data.estimate.output_tokens.high),
        cost:data.estimate.cost_usd==null?tr('cost_unknown'):tr('usd')+' '+num(data.estimate.cost_usd.low)+'–'+num(data.estimate.cost_usd.high)}));
      bind('workload-status',data.bounded?'bounded':'preview_ready');
    }catch(error){if(current===generation)errorStatus(error);}
    finally{if(current===generation)busy(false);}
  };
  window.saveWorkloadBudget=async function(){
    for(const id of ['workload-limit','workload-input-price','workload-output-price'])if(!el(id).reportValidity())return;
    const patch={max_requests:Number(el('workload-limit').value),
      input_price:el('workload-input-price').value===''?null:Number(el('workload-input-price').value),
      output_price:el('workload-output-price').value===''?null:Number(el('workload-output-price').value)};
    const current=++generation;busy(true);bind('workload-status','saving');
    try{
      await request('/__knowledge_budget__',patch);
      if(current===generation&&el('knowledge-settings').open){
        el('workload-preview-result').replaceChildren();bind('workload-status','saved');
      }
    }catch(error){if(current===generation)errorStatus(error);}
    finally{if(current===generation)busy(false);}
  };
  document.addEventListener('DOMContentLoaded',()=>el('knowledge-settings')?.addEventListener('close',()=>{++generation;busy(false);}));
  document.addEventListener('selfos-import-finished',async()=>{
    try{const data=await request('/__knowledge_settings__');window.renderWorkloadUsage(data.usage);}catch(error){}
  });
})();
