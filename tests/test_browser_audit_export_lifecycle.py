import shutil
import subprocess
from selfos.web.rendering.resources import frontend_text


def test_audit_export_preview_and_draft_survive_lifecycle_without_stale_download(tmp_path):
    script = r'''
const assert=require('assert/strict'), nodes=new Map(), requests=[], downloads=[];
function node(id){if(!nodes.has(id))nodes.set(id,{value:'',checked:false,hidden:true,open:false,files:[],listeners:new Map(),showModal(){this.open=true;},close(){this.open=false;this.listeners.get('close')?.();},addEventListener(type,fn){this.listeners.set(type,fn);},removeEventListener(type){this.listeners.delete(type);}});return nodes.get(id);}
global.window=global;global.document={getElementById:node,querySelector:node,addEventListener(){},removeEventListener(){},createElement(){return {click(){downloads.push(this.href);}};}};
global.selfosI18n={has:()=>true,t:(key,values)=>key+JSON.stringify(values||{}),bindText:(element,key,value)=>{element.textContent=value().value;}};
global.fetch=(url,options)=>new Promise(resolve=>requests.push({url,options,resolve}));
global.URL.createObjectURL=()=> 'blob:fixture';global.URL.revokeObjectURL=()=>{};
RUNTIME
selfosUI.register('request',()=>({}));selfosUI.register('locale',()=>({}));
PRIVACY
const settle=async()=>{for(let n=0;n<30;n++)await Promise.resolve();};
const summary={operations:2,bytes:123,oldest:{run_id:'old',index:1},newest:{run_id:'new',index:2},earlier_history_omitted:true};
(async()=>{
 selfosUI.init(document);const privacy=selfosUI.module('privacy'),opening=privacy.open();
 requests[0].resolve({ok:true,json:async()=>({selection:{exclusions:[],privacy_exclusions:[]},destination:{},withheld_sources:0})});await opening;
 node('privacy-audit').value='recent';node('privacy-audit-recent').value='2';node('privacy-originals').checked=true;
 const preparing=privacy.export();assert.deepEqual(JSON.parse(requests[1].options.body),{action:'export',originals:true,backups:false,audit:'recent',audit_recent:2});
 requests[1].resolve({ok:true,json:async()=>({audit_summary:summary,fixture:'prepared'})});await preparing;
 assert.equal(downloads.length,0,'Preparation must show the range before downloading');assert.equal(node('privacy-download').hidden,false);assert.match(node('privacy-status').textContent,/123/);
 privacy.close();const reopening=privacy.open();requests[2].resolve({ok:true,json:async()=>({selection:{exclusions:[],privacy_exclusions:[]},destination:{},withheld_sources:0})});await reopening;
 assert.match(node('privacy-status').textContent,/123/,'Reopening must retain the range preview while its snapshot remains downloadable');
 selfosUI.teardown();selfosUI.init(document);assert.equal(node('privacy-audit').value,'recent');assert.equal(node('privacy-audit-recent').value,'2');assert.equal(node('privacy-download').hidden,false);
 privacy.download();assert.equal(downloads.length,1);
 const stale=privacy.export();assert.equal(node('privacy-download').hidden,true);selfosUI.teardown();assert(requests[3].options.signal.aborted);
 requests[3].resolve({ok:true,json:async()=>({audit_summary:summary,fixture:'stale'})});await stale;selfosUI.init(document);privacy.download();assert.equal(downloads.length,1,'Canceled preparation must not become downloadable after remount');
 selfosUI.teardown();
})().catch(error=>{console.error(error);process.exitCode=1;});
'''.replace('RUNTIME', frontend_text('scripts/ui-runtime.js')).replace('PRIVACY', frontend_text('scripts/privacy.js'))
    path=tmp_path/'audit-export.js';path.write_text(script,encoding='utf-8')
    result=subprocess.run([shutil.which('node'),str(path)],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode == 0, result.stderr
