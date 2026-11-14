import shutil, subprocess
from selfos.web.i18n import runtime
from selfos.web.rendering.resources import frontend_text


def test_language_switch_preserves_import_stream_log_and_stop_state(tmp_path):
    common=runtime().split('<script',1)[1].split('>',1)[1].split('</script>',1)[0]
    script=frontend_text('scripts/ui-runtime.js')+frontend_text('scripts/dashboard-imports.js')
    harness=r"""
const elements=new Map(),listeners=new Map();
function element(id){if(!elements.has(id))elements.set(id,{textContent:'',isConnected:true,disabled:false,style:{},classList:{add(){},remove(){}},addEventListener(){}});return elements.get(id);}
global.window=global;global.localStorage={getItem:()=>null,setItem(){}};
global.document={documentElement:{lang:'en'},getElementById:element,querySelectorAll:()=>[],addEventListener:(k,f)=>{if(!listeners.has(k))listeners.set(k,[]);listeners.get(k).push(f);},dispatchEvent:e=>{for(const f of listeners.get(e.type)||[])f(e);}};
let calls=0,streams=[];global.fetch=async()=>{calls++;return {ok:true,json:async()=>({running:false})};};
global.EventSource=class{constructor(url){this.url=url;streams.push(this);}close(){this.closed=true;}};
function checkStaging(){}
COMMON
IMPORTS
(async()=>{
confirmHarvest(false,true);const stream=streams[0];
stream.onmessage({data:JSON.stringify({line:'Saved session 1/4: source unchanged'})});
const original=element('progress-log').textContent,originalTitle=element('progress-title').textContent,before=calls;
selfosI18n.setLocale('zh');if(streams.length!==1||calls!==before||stream.closed||element('progress-log').textContent!==original||element('progress-title').textContent===originalTitle)throw Error('Switch disturbed live import or kept stale status');
await stopKnowledge();selfosI18n.setLocale('en');if(!element('knowledge-stop-btn').disabled||!element('progress-title').textContent.includes('Stopping'))throw Error('Pending stop state lost');
stream.onmessage({data:JSON.stringify({done:true,ok:true,cancelled:true})});
if(!element('progress-title').textContent.includes('Stopped')||!stream.closed||element('progress-log').textContent!==original)throw Error('Cancelled state/log lost');
selfosI18n.setLocale('zh');if(element('progress-title').textContent.includes('Stopped')||streams.length!==1)throw Error('Terminal state did not translate');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    source=tmp_path/'progress.js';source.write_text(harness.replace('COMMON',common).replace('IMPORTS',script),encoding='utf-8')
    result=subprocess.run([shutil.which('node'),str(source)],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stderr


def test_import_settings_keys_are_declared_and_status_binding_preserves_unsaved_inputs(tmp_path):
    import re
    from selfos.web.i18n import catalogs
    source=frontend_text('scripts/ui-runtime.js')+"selfosUI.register('publication',()=>({render(){}}));"+frontend_text('scripts/import-controls.js')
    template=frontend_text('templates/import-controls.html')
    assert 'knowledgeText' not in source
    assert 'data-zh' not in template and 'data-en' not in template
    messages=catalogs()['locales']['en']['messages']
    for key in re.findall(r"['\"](ui\.[a-zA-Z0-9_.]+)['\"]",source+template):assert key in messages
    common=runtime().split('<script',1)[1].split('>',1)[1].split('</script>',1)[0]
    harness=r"""
const elements=new Map();function element(id){if(!elements.has(id))elements.set(id,{textContent:'',value:'unsaved',disabled:false,isConnected:true});return elements.get(id);}
global.window=global;global.localStorage={getItem:()=>null,setItem(){}};global.document={documentElement:{lang:'en'},getElementById:element,querySelectorAll:()=>[],addEventListener(){},dispatchEvent(){}};
global.fetch=()=>{throw Error('Language switch must not call API');};
COMMON
CONTROLS
displayKnowledgeStatus({last_operation:{id:'backup-fixture'},needs_rebuild:true});
const english=element('knowledge-status').textContent;selfosI18n.setLocale('zh');
if(element('knowledge-status').textContent===english||element('knowledge-custom').value!=='unsaved'||element('knowledge-undo').disabled)throw Error('Import settings state lost');
"""
    path=tmp_path/'controls.js';path.write_text(harness.replace('COMMON',common).replace('CONTROLS',source),encoding='utf-8')
    result=subprocess.run([shutil.which('node'),str(path)],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stderr


def test_progress_states_only_reference_declared_keys():
    import re
    from selfos.web.i18n import catalogs
    source=frontend_text('scripts/dashboard-imports.js')
    assert "lang ===" not in source
    messages=catalogs()['locales']['en']['messages']
    for key in re.findall(r"'(ui\.[a-zA-Z0-9_.]+)'",source):assert key in messages
