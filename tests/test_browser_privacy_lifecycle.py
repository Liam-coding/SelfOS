import shutil
import subprocess
import pytest
from selfos.web.rendering.resources import frontend_text


@pytest.mark.parametrize("queued_close", [False, True])
def test_privacy_cancelled_load_resumes_without_overwriting_dirty_rules(tmp_path, queued_close):
    script=r"""
const assert=require('assert/strict'),nodes=new Map(),requests=[];
function node(id){if(!nodes.has(id))nodes.set(id,{value:'',checked:false,open:false,files:[],listeners:new Map(),showModal(){this.open=true;},close(){this.open=false;const notify=()=>this.listeners.get('close')?.();QUEUED_CLOSE?setTimeout(notify,0):notify();},addEventListener(type,fn){this.listeners.set(type,fn);},removeEventListener(type){this.listeners.delete(type);}});return nodes.get(id);}
global.window=global;global.document={getElementById:node,querySelector:node,addEventListener(){},removeEventListener(){}};global.selfosI18n={has:()=>true,t:key=>key,bindText(){}};
global.fetch=(url,options)=>new Promise(resolve=>requests.push({url,options,resolve}));
RUNTIME
selfosUI.register('request',()=>({}));selfosUI.register('locale',()=>({}));
PRIVACY
(async()=>{
 selfosUI.init(document);const privacy=selfosUI.module('privacy'),opening=privacy.open();assert.equal(requests.length,1);
 node('privacy-rules').value='/dirty-local-draft';node('privacy-rules').listeners.get('input')();
 selfosUI.init(document);selfosUI.init(document);assert.equal(requests.length,1);
 selfosUI.teardown();assert(requests[0].options.signal.aborted);requests[0].resolve({ok:true,json:async()=>({selection:{exclusions:['/old'],privacy_exclusions:[]},destination:{},withheld_sources:0})});await opening;
 selfosUI.init(document);assert.equal(requests.length,2);await new Promise(resolve=>setTimeout(resolve,10));requests[1].resolve({ok:true,json:async()=>({selection:{exclusions:['/new'],privacy_exclusions:[]},destination:{model:'Loaded destination'},withheld_sources:0})});for(let n=0;n<20;n++)await Promise.resolve();
 assert.equal(node('privacy-rules').value,'/dirty-local-draft');assert.equal(node('privacy-destination').textContent,'Loaded destination');
 window.selfosReadOnlyDemo=true;privacy.save();privacy.export();privacy.import({size:2,text:async()=>'{}'});for(let n=0;n<20;n++)await Promise.resolve();assert.equal(requests.length,2,'Demo sent mutation');
 selfosUI.teardown();
})().catch(error=>{console.error(error);process.exitCode=1;});
""".replace('QUEUED_CLOSE',str(queued_close).lower()).replace('RUNTIME',frontend_text('scripts/ui-runtime.js')).replace('PRIVACY',frontend_text('scripts/privacy.js'))
    path=tmp_path/'privacy.js';path.write_text(script,encoding='utf-8')
    result=subprocess.run([shutil.which('node'),str(path)],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stderr
