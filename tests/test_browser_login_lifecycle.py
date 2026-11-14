import json
import shutil
import subprocess
from selfos.web.rendering.resources import frontend_text


def test_login_inert_registration_single_status_read_and_secret_cleanup(tmp_path):
    script=r"""
const vm=require('vm'),assert=require('assert/strict'),nodes=new Map(),requests=[];let reads=0,redirects=0;
function node(id){if(!nodes.has(id))nodes.set(id,{value:'',dataset:{},hidden:false,disabled:false,classList:{toggle(){}},listeners:new Map(),addEventListener(type,fn){this.listeners.set(type,fn);},removeEventListener(type){this.listeners.delete(type);}});return nodes.get(id);}
global.window=global;global.document={body:node('body'),getElementById:node,querySelector:node};global.localStorage={getItem(){reads++;return null;}};global.location={replace(){redirects++;}};global.selfosI18n={locale:'en',populateLanguageSelect(){},translate(){},setLocale(){},has:()=>true,t:key=>key,bindText(){}};
global.fetch=(url,options={})=>new Promise(resolve=>requests.push({url,options,resolve}));
RUNTIME
selfosUI.register('request',()=>({}));selfosUI.register('locale',()=>({}));
AUTH
LOGIN
(async()=>{
 const login=selfosUI.module('login');assert.equal(reads,0);assert.equal(requests.length,0);
 selfosUI.init(document);selfosUI.init(document);vm.runInThisContext(LOGIN_JSON);selfosUI.init(document);assert.equal(requests.length,1);
 requests[0].resolve({ok:true,json:async()=>({state:'setup',authenticated:false})});for(let n=0;n<20;n++)await Promise.resolve();
 node('auth-password').value='synthetic credential';node('auth-confirm').value='synthetic credential';const submitting=login.submit({preventDefault(){}});assert.equal(requests.length,2);assert.equal(requests[1].url,'/auth/setup');
 selfosUI.teardown();assert(requests[1].options.signal.aborted);assert.equal(node('auth-password').value,'');assert.equal(node('auth-confirm').value,'');
 requests[1].resolve({ok:true,json:async()=>({})});await submitting;assert.equal(redirects,0);
 selfosUI.init(document);assert.equal(requests.length,3);assert.equal(requests[2].url,'/auth/status');selfosUI.teardown();assert(requests[2].options.signal.aborted);
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    login=frontend_text('scripts/login.js')
    script=script.replace('RUNTIME',frontend_text('scripts/ui-runtime.js')).replace('AUTH',frontend_text('scripts/auth-common.js')).replace('LOGIN_JSON',json.dumps(login)).replace('LOGIN',login)
    path=tmp_path/'login.js';path.write_text(script,encoding='utf-8')
    result=subprocess.run([shutil.which('node'),str(path)],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stderr
