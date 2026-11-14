(function(window){
'use strict';
window.selfosUI.register('usage',()=>{
const requests=new Set(),cleanups=[];
function on(node,type,callback){node?.addEventListener?.(type,callback);cleanups.push(()=>node?.removeEventListener?.(type,callback));}
  const el=id=>document.getElementById(id);
  const num=value=>window.selfosI18n.number(value);
  const bind=(id,key,values={})=>{if(el(id))window.selfosI18n.bindText(id,'workload.'+key,values);};
  let generation=0, timer=null, fetching=false, queued=false, usageGeneration=0;
  function busy(value){if(el('workload-save'))el('workload-save').disabled=value;}
  async function request(url,body){
    const controller=new AbortController();requests.add(controller);try{const response=await fetch(url,{signal:controller.signal,...(body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
    const data=await response.json();
    if(!response.ok){const error=new Error('usage_request_failed');error.code=data.code;throw error;}
    return data;}finally{requests.delete(controller);}
  }
  function errorStatus(error){bind('workload-status',error.code==='budget_import_active'?'active':error.code==='budget_invalid'?'invalid':'failed');}
  function renderWorkloadUsage(data,populate=false){
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
    try{const data=await request('/__knowledge_usage__');if(current===usageGeneration)renderWorkloadUsage(data);}
    catch(error){if(current===usageGeneration){for(const id of ['workload-usage','workload-progress-usage'])bind(id,'unavailable');}}
    finally{if(current===usageGeneration){fetching=false;if(queued){queued=false;refreshUsage();}}}
  }
  function startUsage(){
    if(timer!==null)return;
    refreshUsage();timer=setInterval(refreshUsage,1500);
  }
  async function saveWorkloadBudget(){
    if(window.selfosReadOnlyDemo||!el('workload-limit').reportValidity())return;
    const current=++generation;busy(true);bind('workload-status','saving');
    try{
      await request('/__knowledge_budget__',{max_requests:Number(el('workload-limit').value)});
      if(current===generation&&el('knowledge-settings').open)bind('workload-status','saved');
    }catch(error){if(current===generation)errorStatus(error);}
    finally{if(current===generation)busy(false);}
  };

function init(){
 ++usageGeneration;
 on(el('knowledge-settings'),'close',()=>{++generation;busy(false);});
 on(el('workload-save'),'click',saveWorkloadBudget);
 const jobs=window.selfosUI.module('jobs');
 cleanups.push(jobs.subscribe(state=>{
  if(state.kind!=='knowledge')return;
  if(state.running)startUsage();
  else if(state.event==='finished'){if(timer!==null)clearInterval(timer);timer=null;refreshUsage();}
 }));
 if(jobs.snapshot().running&&jobs.snapshot().kind==='knowledge')startUsage();else refreshUsage();
}
function teardown(){++generation;++usageGeneration;if(timer!==null)clearInterval(timer);timer=null;for(const controller of requests)controller.abort();requests.clear();fetching=false;queued=false;cleanups.splice(0).reverse().forEach(cleanup=>cleanup());}
return {render:renderWorkloadUsage,save:saveWorkloadBudget,refresh:refreshUsage,busy:()=>requests.size>0,init,teardown};
},{dependencies:['jobs','request','locale'],roots:['#workload-controls']});
for(const [name,method]of Object.entries({renderWorkloadUsage:'render',saveWorkloadBudget:'save'}))if(!window[name])window[name]=(...args)=>window.selfosUI.module('usage')[method](...args);
})(window);
