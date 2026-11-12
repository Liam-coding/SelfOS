import shutil,subprocess
from selfos.web.i18n import runtime
from selfos.web.rendering.resources import frontend_text


def test_staging_keeps_literal_filenames_selection_and_pending_apply(tmp_path):
 common=runtime().split('<script',1)[1].split('>',1)[1].split('</script>',1)[0]
 script=frontend_text('scripts/dashboard-staging.js')
 harness=r"""
const elements=new Map(),listeners=new Map(),rows=[];
function create(){return {textContent:'',dataset:{},style:{},disabled:false,isConnected:true,children:[],set innerHTML(v){throw Error('Unsafe filename HTML');},append(...nodes){this.children.push(...nodes);},appendChild(n){this.children.push(n);rows.push(n);},replaceChildren(){this.children=[];},addEventListener(){},classList:{add(){},remove(){},toggle(){}}};}
function element(id){if(!elements.has(id))elements.set(id,create());return elements.get(id);}
global.window=global;global.localStorage={getItem:()=>null,setItem(){}};global.document={documentElement:{lang:'en'},getElementById:element,querySelectorAll:s=>s==='.staging-file-item.selected'?rows:[],createElement:create,addEventListener:(k,f)=>{if(!listeners.has(k))listeners.set(k,[]);listeners.get(k).push(f);},dispatchEvent:e=>{for(const f of listeners.get(e.type)||[])f(e);}};
const name='<img src=x onerror=unsafe()>',files=[{name,target:''}];let calls=0,finishApply;
global.fetch=async(url,options)=>{calls++;if(url==='/__staging__/apply'){if(JSON.parse(options.body).files[0]!==name)throw Error('Filename changed');return await new Promise(resolve=>finishApply=()=>resolve({ok:true,json:async()=>({ok:true})}));}return {ok:true,json:async()=>({files})};};
COMMON
STAGING
(async()=>{
for(let n=0;n<20;n++)await Promise.resolve();openStagingModal();
if(rows[0].children[0].textContent!==name)throw Error('Literal filename not preserved');
const row=rows[0],before=calls;selfosI18n.setLocale('zh');if(calls!==before||rows[0]!==row)throw Error('Switch replaced selection or refetched');
applySelectedStaging();for(let n=0;n<20&&!finishApply;n++)await Promise.resolve();selfosI18n.setLocale('en');
if(!element('staging-apply-btn').disabled||element('staging-apply-btn').textContent!=='Applying...')throw Error('Pending apply state lost');
finishApply();for(let n=0;n<20;n++)await Promise.resolve();if(element('staging-apply-btn').disabled)throw Error('Apply remained disabled');
global.fetch=async()=>({ok:false,json:async()=>({ok:false})});
applySelectedStaging();for(let n=0;n<20;n++)await Promise.resolve();
if(element('staging-apply-btn').disabled||!element('staging-apply-btn').textContent.includes('Could not'))throw Error('HTTP failure presented as success');
global.fetch=async()=>({ok:true,json:async()=>({ok:true,applied:[],errors:['synthetic apply error']})});
applySelectedStaging();for(let n=0;n<20;n++)await Promise.resolve();if(!element('staging-apply-btn').textContent.includes('Could not'))throw Error('Partial operation errors ignored');
const failure=element('staging-apply-btn').textContent;selfosI18n.setLocale('zh');if(element('staging-apply-btn').textContent===failure||rows[0]!==row)throw Error('Failure translation lost selection');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
 path=tmp_path/'staging.js';path.write_text(harness.replace('COMMON',common).replace('STAGING',script),encoding='utf-8')
 result=subprocess.run([shutil.which('node'),str(path)],capture_output=True,text=True,encoding='utf-8')
 assert result.returncode==0,result.stderr
