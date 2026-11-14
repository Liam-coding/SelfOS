(function(window){
  'use strict';
  window.selfosUI.register('jobs',()=>{
    let running=false,kind=null,phase='idle',transport=null,stream=null,timer=null,generation=0,lifetime=0,runId=0,stopSent=false,stopRequest=null,lastEvent='idle';
    const requests=new Set(),subscribers=new Set(),cleanups=[];
    const el=id=>document.getElementById(id);
    const snapshot=()=>Object.freeze({kind,phase,running,transport,runId,event:lastEvent});
    const status=key=>window.selfosI18n.bindText('progress-title',key);
    function notify(event){
      lastEvent=event;const state=snapshot();
      for(const subscriber of subscribers)subscriber(state);
      if(kind==='knowledge'&&(event==='started'||event==='finished'))document.dispatchEvent(new Event('selfos-import-'+event));
    }
    async function request(url,options={},readJson=true){
      const controller=new AbortController();requests.add(controller);
      try{const response=await fetch(url,{...options,signal:controller.signal});if(!response.ok)throw Error('job_request_failed');return readJson?await response.json():response;}
      finally{requests.delete(controller);}
    }
    function clearTransport(){
      if(stream){const current=stream;stream=null;current.close();}
      if(timer!==null){clearTimeout(timer);timer=null;}
      transport=null;
    }
    function openHarvest(){el('harvest-modal').classList.add('open');}
    function closeHarvest(){el('harvest-modal').classList.remove('open');}
    function showProgress(recovering=false){
      closeHarvest();el('progress-modal').classList.add('open');el('progress-done-btn').style.display='none';
      el('knowledge-stop-btn').style.display=kind==='knowledge'?'block':'none';el('knowledge-stop-btn').disabled=stopSent;
      if(!recovering){el('progress-bar').style.width='0%';el('progress-log').textContent='';el('progress-icon').textContent='\u23f3';}
    }
    function finish(result,recovered=false){
      if(!running)return;
      clearTransport();running=false;phase=result.cancelled?'cancelled':result.ok?'succeeded':'failed';++generation;
      for(const controller of requests)controller.abort();requests.clear();stopSent=false;stopRequest=null;
      const successful=result.ok&&!result.cancelled;
      if(successful)el('progress-bar').style.width='100%';
      el('knowledge-stop-btn').style.display='none';el('progress-icon').textContent=result.ok&&(!recovered||!result.cancelled)?'\u2705':'\u26a0\ufe0f';
      status(result.cancelled?(recovered?'ui.import.stopped_progress_saved_resume_available':'ui.import.stopped_resume_available'):result.ok?(kind==='knowledge'?'ui.import.knowledge_complete':'ui.import.harvest_complete'):'ui.import.incomplete_retry_available');
      el('progress-done-btn').style.display='block';window.selfosI18n.bindText(el('progress-done-btn'),'ui.import.done_refresh');notify('finished');
    }
    function schedule(callback,delay){if(timer!==null)clearTimeout(timer);timer=setTimeout(()=>{timer=null;callback();},delay);}
    function recover(initialState){
      if(running&&kind==='harvest')return snapshot();
      if(running&&transport?.startsWith('recovery:'))return snapshot();
      const alreadyRunning=running&&kind==='knowledge';clearTransport();running=true;kind='knowledge';phase='recovering';const token=++generation;
      if(!alreadyRunning){++runId;stopSent=false;}transport='recovery:'+token;showProgress(true);status('ui.import.checking_knowledge_task_status');notify(alreadyRunning?'transition':'started');
      function apply(state){
        if(token!==generation||!running)return;
        if(state.total)el('progress-bar').style.width=Math.max(parseFloat(el('progress-bar').style.width)||0,10+Math.round(80*state.completed/state.total))+'%';
        if(state.running){
          phase=state.phase==='stopping'||stopSent?'stopping':'recovering';status(phase==='stopping'?'ui.import.stopping_and_saving_progress':'ui.import.task_is_running_syncing_status');schedule(poll,1500);
        }else finish(state.result||{ok:false},true);
      }
      async function poll(){
        try{const state=await request('/__knowledge_run__',{cache:'no-store'});apply(state);}
        catch(error){if(token!==generation||!running)return;status('ui.import.server_unavailable_retrying_status');schedule(poll,2000);}
      }
      if(initialState)apply(initialState);else poll();return snapshot();
    }
    function start(full=false,knowledge=false,rebuild=false,previewUrl=null){
      if(running||window.selfosReadOnlyDemo)return snapshot();
      clearTransport();for(const controller of requests)controller.abort();requests.clear();
      running=true;kind=knowledge?'knowledge':'harvest';phase='running';stopSent=false;stopRequest=null;++runId;const token=++generation;showProgress();
      status(knowledge?'ui.import.building_knowledge':'ui.import.harvesting');
      const url=knowledge?(previewUrl||'/__knowledge_stream__'+(rebuild?'?action=rebuild':'')):'/__harvest_stream__?full='+(full?'1':'0');
      let current;
      try{current=new EventSource(url);}catch(error){finish({ok:false});return snapshot();}
      stream=current;transport='stream:'+token;notify('started');
      let percent=0;const saved=new Set();
      const advance=value=>{if(value>percent){percent=value;el('progress-bar').style.width=value+'%';}};
      const steps=[['SelfOS Harvest',5],['Extracting',20],['extraction',30],['build_session',50],['digest',60],['Scoring',75],['Dashboard',88],['Done',100]];
      current.onmessage=event=>{
        if(token!==generation||stream!==current||!running)return;
        let message;try{message=JSON.parse(event.data);}catch(error){return;}
        if(message.done){finish(message);return;}
        const line=message.line||'';if(typeof line!=='string'||!line.trim())return;
        const log=el('progress-log');log.textContent+=(log.textContent?'\n':'')+line;log.scrollTop=log.scrollHeight;
        if(knowledge){
          const batch=line.match(/(?:Organizing|Saved) (?:batch|session) ([0-9]+)\/([0-9]+)/);
          if(batch&&Number(batch[2])>0){if(line.startsWith('Saved'))saved.add(batch[1]);advance(10+Math.round(80*saved.size/Number(batch[2])));}
          else if(line.includes('Knowledge:'))advance(10);
        }else for(const [keyword,value]of steps)if(line.toLowerCase().includes(keyword.toLowerCase())){advance(value);break;}
      };
      current.onerror=()=>{
        if(token!==generation||stream!==current||!running)return;
        stream=null;current.close();transport=null;
        if(knowledge){recover();return;}
        finish({ok:false});status('ui.import.connection_lost');
      };
      return snapshot();
    }
    function stop(){
      if(!running||kind!=='knowledge'||window.selfosReadOnlyDemo)return Promise.resolve(snapshot());
      if(stopSent)return stopRequest||Promise.resolve(snapshot());
      stopSent=true;el('knowledge-stop-btn').disabled=true;const owner=lifetime,identity=runId;
      stopRequest=(async()=>{
        try{await request('/__knowledge_stop__',{method:'POST'},false);if(owner!==lifetime||identity!==runId||!running)return snapshot();phase='stopping';status('ui.import.stopping_saving_completed_results');notify('transition');}
        catch(error){if(owner!==lifetime||identity!==runId||!running)return snapshot();stopSent=false;el('knowledge-stop-btn').disabled=false;status('ui.import.stop_failed');}
        return snapshot();
      })();return stopRequest;
    }
    function init(){
      ++lifetime;
      function action(event){
        const node=event.target.closest?.('[data-selfos-action]');if(!node||!document.contains(node)||!node.closest('#harvest-modal,#progress-modal,#knowledge-btn,#harvest-btn'))return;
        const actions={'jobs.open':openHarvest,'jobs.close':closeHarvest,'jobs.knowledge':()=>start(false,true),'jobs.incremental':()=>start(false),'jobs.full':()=>start(true),'jobs.stop':stop,'jobs.reload':()=>location.reload()};
        if(!Object.hasOwn(actions,node.dataset.selfosAction))return;event.preventDefault();actions[node.dataset.selfosAction]();
      }
      document.addEventListener('click',action);cleanups.push(()=>document.removeEventListener('click',action));
      const modal=el('harvest-modal'),backdrop=event=>{if(event.target===event.currentTarget)closeHarvest();};modal.addEventListener('click',backdrop);cleanups.push(()=>modal.removeEventListener('click',backdrop));
      if(running)return;
      phase='checking';const token=++generation;
      request('/__knowledge_run__',{cache:'no-store'}).then(state=>{if(token!==generation)return;if(state&&state.running)recover(state);else{kind=null;phase='idle';transport=null;}}).catch(()=>{if(token===generation)phase='idle';});
    }
    function teardown(){++lifetime;++generation;clearTransport();for(const controller of requests)controller.abort();requests.clear();if(running)phase='detached';running=false;stopSent=false;stopRequest=null;subscribers.clear();cleanups.splice(0).reverse().forEach(cleanup=>cleanup());}
    return {start,recover,stop,snapshot,subscribe(callback){if(typeof callback!=='function')throw Error('Invalid jobs subscriber');subscribers.add(callback);return()=>subscribers.delete(callback);},open:openHarvest,close:closeHarvest,busy:()=>running||requests.size>0,init,teardown};
  },{dependencies:['request','locale'],roots:['#harvest-modal','#progress-modal']});
  for(const [name,method]of Object.entries({confirmHarvest:'start',recoverKnowledgeRun:'recover',stopKnowledge:'stop',openHarvestModal:'open',closeHarvestModal:'close'}))if(!window[name])window[name]=(...args)=>window.selfosUI.module('jobs')[method](...args);
})(window);
