import json
import shutil
import subprocess
from selfos.web.rendering.resources import frontend_text


def test_knowledge_family_is_inert_and_aborts_every_pending_body_on_teardown(tmp_path):
    script=r"""
const vm=require('vm'),assert=require('assert/strict'),nodes=new Map(),requests=[];let writes=0;
class Element{constructor(){this.value='';this.children=[];this.dataset={};this.style={};this.open=false;this.listeners=new Map();this.isConnected=true;}append(...children){writes++;this.children.push(...children);}replaceChildren(...children){writes++;this.children=children;}setAttribute(){writes++;}addEventListener(type,fn){this.listeners.set(type,fn);}removeEventListener(type){this.listeners.delete(type);}querySelectorAll(){return [];}querySelector(){return null;}focus(){}showModal(){this.open=true;}close(){this.open=false;this.listeners.get('close')?.();}scrollIntoView(){}}
function node(id){if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);}
global.window=global;global.document={getElementById:node,querySelector:selector=>selector.startsWith('#')?node(selector.slice(1)):null,querySelectorAll:()=>[],createElement:()=>new Element(),createTextNode:()=>new Element(),addEventListener(){},removeEventListener(){}};global.selfosI18n={has:()=>false,t:key=>key,number:String,bindText(){writes++;},date:String};global.matchMedia=()=>({matches:true});
global.fetch=(url,options)=>new Promise(resolve=>requests.push({url,options,resolve}));
RUNTIME
selfosUI.register('request',()=>({}));selfosUI.register('locale',()=>({}));
OWNERS
(async()=>{
 assert.equal(writes,0,'Factory/script wrote UI before mount');selfosUI.init(document);assert.equal(requests.length,1);
 const knowledge=selfosUI.module('knowledge'),timeline=selfosUI.module('timeline'),corrections=selfosUI.module('corrections');
 const detail=knowledge.openDetail('pending-record'),chronology=timeline.open('project'),history=corrections.history(new Element(),()=>{});assert.equal(requests.length,4);
 selfosUI.init(document);selfosUI.init(document);vm.runInThisContext(OWNERS_JSON);selfosUI.init(document);assert.equal(requests.length,4);
 selfosUI.teardown();assert(requests.every(request=>request.options.signal.aborted),'Owner leaked pending request');writes=0;
 for(const request of requests)request.resolve({ok:true,json:async()=>({items:[],total:0,actions:[],item:{},sources:[],source_count:0,current:null})});
 await Promise.all([detail,chronology,history]);for(let n=0;n<20;n++)await Promise.resolve();assert.equal(writes,0,'Stale body wrote UI after teardown');
 selfosUI.init(document);selfosUI.teardown();
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    owners=''.join(frontend_text('scripts/'+name) for name in ['knowledge-corrections.js','project-timeline.js','knowledge-browser.js'])
    script=script.replace('RUNTIME',frontend_text('scripts/ui-runtime.js')).replace('OWNERS_JSON',json.dumps(owners)).replace('OWNERS',owners)
    path=tmp_path/'knowledge.js';path.write_text(script,encoding='utf-8')
    result=subprocess.run([shutil.which('node'),str(path)],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stderr
