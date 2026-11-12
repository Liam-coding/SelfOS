import shutil
import subprocess
from selfos.web.i18n import runtime
from selfos.web.rendering.resources import frontend_text


def test_overview_switch_updates_status_counts_without_fetching_again(tmp_path):
    common = runtime().split('<script', 1)[1].split('>', 1)[1].split('</script>', 1)[0]
    script = frontend_text('scripts/overview.js')
    harness = r"""
const elements=new Map(),listeners=new Map();
function element(id){if(!elements.has(id))elements.set(id,{textContent:'',isConnected:true,classList:{add(){},remove(){}}});return elements.get(id);}
global.window=global;global.localStorage={getItem:()=>null,setItem(){}};
global.document={documentElement:{lang:'en'},getElementById:element,querySelectorAll:()=>[],addEventListener:(k,f)=>{if(!listeners.has(k))listeners.set(k,[]);listeners.get(k).push(f);},dispatchEvent:e=>{for(const f of listeners.get(e.type)||[])f(e);}};
let calls=0;global.fetch=async()=>{calls++;return {ok:true,json:async()=>({saved_checkpoints:1234,counts:{cards:1234}})};};
COMMON
OVERVIEW
(async()=>{
await updateKnowledgeOverview();
if(!element('knowledge-count-cards').textContent.includes('1,234'))throw Error('Count not locale formatted');
const original=element('knowledge-overview-status').textContent;
selfosI18n.setLocale('zh');if(calls!==1||element('knowledge-overview-status').textContent===original)throw Error('Switch refetched or retained status');
selfosI18n.setLocale('en');if(element('knowledge-overview-status').textContent!==original||calls!==1)throw Error('Switch lost retained overview state');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    source = tmp_path / 'runtime.js'
    source.write_text(harness.replace('COMMON', common).replace('OVERVIEW', script), encoding='utf-8')
    result = subprocess.run([shutil.which('node'), str(source)], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr


def test_dashboard_language_glue_uses_shared_runtime_without_requests(tmp_path):
    script = frontend_text('scripts/dashboard-theme-language.js')
    assert "let lang = window.selfosI18n.documentTag" in script
    assert 'updateKnowledgeOverview();' not in script
    assert 'data-zh' not in script
    assert 'selfosI18n.setLocale' in script
