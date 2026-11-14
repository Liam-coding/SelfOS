"""Exercise transport ownership against synthetic browser boundaries."""
import shutil
import subprocess
from pathlib import Path


def test_jobs_one_transport_kind_specific_recovery_stop_and_teardown():
    scripts=Path(__file__).parents[1]/'src/selfos/resources/web/scripts'
    result=subprocess.run([shutil.which('node'),'-e',r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
global.window=global;const nodes=new Map(),events=[],timers=new Map();let timerSequence=0;
function node(id){if(!nodes.has(id))nodes.set(id,{style:{},textContent:'',disabled:false,dataset:{},classList:{add(){},remove(){}},addEventListener(){},removeEventListener(){}});return nodes.get(id);}
global.document={getElementById:node,querySelector:s=>node(s),addEventListener(){},removeEventListener(){},dispatchEvent:e=>events.push(e.type),contains:()=>true};
global.selfosI18n={bindText(){},number:String,t:k=>k};global.location={replace(){}};
global.setTimeout=callback=>{const id=++timerSequence;timers.set(id,callback);return id};global.clearTimeout=id=>timers.delete(id);
const requests=[],pending=[],streams=[];
global.fetch=(url,options={})=>{
 const entry={url,options};requests.push(entry);
 if(url==='/__knowledge_stop__')return Promise.resolve({ok:true,status:200,json:async()=>({})});
 assert.equal(url,'/__knowledge_run__','Unexpected startup or provider request');
 return new Promise((resolve,reject)=>{entry.release=state=>resolve({ok:true,status:200,json:async()=>state});pending.push(entry);options.signal?.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true});});
};
global.EventSource=class{constructor(url){this.url=url;this.closed=0;streams.push(this)}close(){this.closed++}};
for(const name of ['ui-runtime.js','ui-request.js','dashboard-imports.js'])vm.runInThisContext(fs.readFileSync(process.argv[1]+'/'+name,'utf8'));
selfosUI.register('locale',()=>selfosI18n);const jobs=selfosUI.module('jobs');
const tick=async()=>{for(let n=0;n<15;n++)await Promise.resolve()};
const release=async state=>{const entry=pending.shift();assert(entry,'Missing status request');entry.release(state);await tick();return entry};
(async()=>{
 selfosUI.init(document);assert.equal(requests.length,1);await release({running:false});
 selfosUI.init(document);selfosUI.init(document);vm.runInThisContext(fs.readFileSync(process.argv[1]+'/dashboard-imports.js','utf8'));selfosUI.init(document);
 assert.equal(requests.length,1);assert.equal(streams.length,0);
 const notifications=[];jobs.subscribe(state=>notifications.push(state));
 jobs.start(false,true);assert.equal(node('progress-icon').textContent,'\u23f3');jobs.start(true,false);assert.equal(streams.length,1);assert.equal(jobs.snapshot().kind,'knowledge');assert(Object.isFrozen(jobs.snapshot()));
 const knowledge=streams[0];selfosUI.init(document);assert.equal(knowledge.closed,0);assert.equal(streams.length,1);
 await Promise.all([jobs.stop(),jobs.stop()]);assert.equal(requests.filter(r=>r.url==='/__knowledge_stop__').length,1);
 knowledge.onmessage({data:JSON.stringify({done:true,ok:true,cancelled:true})});knowledge.onmessage({data:JSON.stringify({done:true,ok:true})});
 assert.equal(knowledge.closed,1);assert.equal(jobs.snapshot().phase,'cancelled');assert.equal(node('progress-icon').textContent,'\u2705');assert.equal(events.filter(e=>e==='selfos-import-finished').length,1);
 assert.equal(notifications.filter(s=>s.event==='finished').length,1);
 jobs.start(true,false);const harvest=streams[1],statusBefore=requests.filter(r=>r.url==='/__knowledge_run__').length;
 harvest.onerror();await tick();assert.equal(harvest.closed,1);assert.equal(jobs.snapshot().kind,'harvest');assert.equal(jobs.snapshot().phase,'failed');assert.equal(node('progress-icon').textContent,'\u26a0\ufe0f');
 await jobs.stop();assert.equal(requests.filter(r=>r.url==='/__knowledge_stop__').length,1);assert.equal(requests.filter(r=>r.url==='/__knowledge_run__').length,statusBefore);assert.equal(timers.size,0);
 jobs.start(false,true);const interrupted=streams[2];interrupted.onerror();assert.equal(interrupted.closed,1);
 await release({running:true,total:4,completed:1,phase:'running'});assert.equal(timers.size,1);
 const timer=[...timers][0];timers.delete(timer[0]);timer[1]();await tick();const active=pending[0];assert(active);
 const stopBefore=requests.filter(r=>r.url==='/__knowledge_stop__').length;selfosUI.teardown();assert.equal(timers.size,0);assert(active.options.signal.aborted);
 active.release({running:false,result:{ok:true}});await tick();pending.shift();assert.equal(events.filter(e=>e==='selfos-import-finished').length,1);assert.equal(requests.filter(r=>r.url==='/__knowledge_stop__').length,stopBefore);assert.equal(streams.length,3);
 selfosUI.init(document);await release({running:true,total:4,completed:2,phase:'running'});assert.equal(streams.length,3);assert.equal(jobs.snapshot().kind,'knowledge');assert.equal(timers.size,1);
 const recovered=[...timers][0];timers.delete(recovered[0]);recovered[1]();await tick();await release({running:false,result:{ok:true},total:4,completed:4});
 assert.equal(jobs.snapshot().phase,'succeeded');assert.equal(node('progress-icon').textContent,'\u2705');assert.equal(timers.size,0);assert.equal(events.filter(e=>e==='selfos-import-finished').length,2);selfosUI.teardown();
 console.log('Jobs lifecycle transport contract passed');
})().catch(error=>{console.error(error);process.exitCode=1});
""",str(scripts)],capture_output=True,text=True,encoding='utf-8',timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
