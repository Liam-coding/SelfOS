(function(){
  const el=id=>document.getElementById(id);
  const num=value=>window.selfosI18n.number(value);
  const bind=(id,key,values={})=>{if(el(id))window.selfosI18n.bindText(id,'workload.'+key,values);};
  let generation=0, timer=null, fetching=false, queued=false, usageGeneration=0;
  function busy(value){if(el('workload-save'))el('workload-save').disabled=value;}
  async function request(url,body){
    const response=await fetch(url,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await response.json();
    if(!response.ok){const error=new Error('usage_request_failed');error.code=data.code;throw error;}
    return data;
  }
  function errorStatus(error){bind('workload-status',error.code==='budget_import_active'?'active':error.code==='budget_invalid'?'invalid':'failed');}
  window.renderWorkloadUsage=function(data,populate=false){
    if(!data)return;
    if(populate&&el('workload-limit'))el('workload-limit').value=data.budget.max_requests;
    const run=data.runs?.[0];
    for(const id of ['workload-usage','workload-progress-usage']){
      if(!run){bind(id,'empty_usage');continue;}
      bind(id,'usage',()=>({used:num(run.used),limit:num(run.limit),
        input:num(run.input_tokens),output:num(run.output_tokens),total:num(run.total_tokens),
        cached:num(run.cache_read_tokens),created:num(run.cache_creation_tokens),failed:num(run.failed_attempts),
        seconds:num(Math.round(run.elapsed_seconds)),missing:num(run.missing_usage)}));
    }
  };
  async function refreshUsage(){
    if(fetching){queued=true;return;}
    fetching=true;const current=usageGeneration;
    try{const data=await request('/__knowledge_usage__');if(current===usageGeneration)window.renderWorkloadUsage(data);}
    catch(error){if(current===usageGeneration){for(const id of ['workload-usage','workload-progress-usage'])bind(id,'unavailable');}}
    finally{fetching=false;if(queued){queued=false;refreshUsage();}}
  }
  function startUsage(){
    ++usageGeneration;if(timer!==null)clearInterval(timer);
    refreshUsage();timer=setInterval(refreshUsage,1500);
  }
  window.saveWorkloadBudget=async function(){
    if(!el('workload-limit').reportValidity())return;
    const current=++generation;busy(true);bind('workload-status','saving');
    try{
      await request('/__knowledge_budget__',{max_requests:Number(el('workload-limit').value)});
      if(current===generation&&el('knowledge-settings').open)bind('workload-status','saved');
    }catch(error){if(current===generation)errorStatus(error);}
    finally{if(current===generation)busy(false);}
  };
  document.addEventListener('DOMContentLoaded',()=>el('knowledge-settings')?.addEventListener('close',()=>{++generation;busy(false);}));
  document.addEventListener('selfos-import-started',startUsage);
  document.addEventListener('selfos-import-finished',()=>{
    if(timer!==null)clearInterval(timer);timer=null;
    // Refresh again after any in-flight response so final usage is current.
    refreshUsage();
  });
})();
