import shutil
import subprocess
from selfos.web.i18n import runtime
from selfos.web.rendering.resources import frontend_text


def test_switching_language_preserves_unsaved_settings_and_pending_model_test(tmp_path):
    common = runtime().split('<script', 1)[1].split('>', 1)[1].split('</script>', 1)[0]
    script = frontend_text('scripts/ui-runtime.js')+frontend_text('scripts/settings-model.js')
    harness = r"""
const elements=new Map(),listeners=new Map();
function element(id){if(!elements.has(id))elements.set(id,{dataset:{},value:'',checked:false,disabled:false,textContent:'',isConnected:true,hidden:false,children:[],append(e){this.children.push(e);},replaceChildren(){this.children=[];},showModal(){this.open=true;},style:{}});return elements.get(id);}
const buttons=[element('save'),element('test')],form={reportValidity:()=>true,querySelectorAll:()=>buttons};
global.window=global;global.localStorage={getItem:()=>null,setItem(){}};
global.document={documentElement:{lang:'en'},getElementById:element,querySelectorAll:()=>[],createElement:()=>({}),querySelector:s=>s==='#model-settings form'?form:null,addEventListener:(k,f)=>{if(!listeners.has(k))listeners.set(k,[]);listeners.get(k).push(f);},dispatchEvent:e=>{for(const f of listeners.get(e.type)||[])f(e);}};
let calls=0,resolveTest;
const config={provider:'anthropic',model:'',proxy_source:'direct',effective_proxy:{},has_api_key:false};
global.fetch=async(url)=>{calls++;if(url==='/__model_test__')return await new Promise(resolve=>resolveTest=()=>resolve({ok:true,json:async()=>({ok:true,message:'RAW PROVIDER MESSAGE'})}));return {ok:true,json:async()=>config};};
COMMON
SETTINGS
(async()=>{
showCurrentModel(config);
element('model-name').value='unsaved-model';element('model-proxy-url').value='http://unsaved:7890';
setSettingsLanguage('zh');
if(!element('current-model').textContent.includes('\u9ed8\u8ba4'))throw Error('Current model did not translate');
if(element('model-name').value!=='unsaved-model'||element('model-proxy-url').value!=='http://unsaved:7890'||calls!==0)throw Error('Language switch mutated form or requested settings');
const pending=saveModelSettings(true);for(let n=0;n<20&&!resolveTest;n++)await Promise.resolve();
if(!resolveTest||!buttons.every(b=>b.disabled))throw Error('No pending test');
const before=calls;setSettingsLanguage('en');
if(!element('model-status').textContent.includes('Testing')||calls!==before||!buttons.every(b=>b.disabled))throw Error('Pending test lost on switch');
resolveTest();await pending;
if(!element('model-status').textContent.includes('passed')||buttons.some(b=>b.disabled))throw Error('Test result or button state failed');
setSettingsLanguage('zh');if(element('model-status').textContent.includes('RAW PROVIDER MESSAGE')||!element('model-status').textContent.includes('\u901a\u8fc7'))throw Error('Completed result did not translate');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    source = tmp_path / 'runtime.js'
    source.write_text(harness.replace('COMMON', common).replace('SETTINGS', script), encoding='utf-8')
    result = subprocess.run([shutil.which('node'), str(source)], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr


def test_model_template_uses_keys_for_labels_and_placeholders(tmp_path):
    from selfos.web.i18n import catalogs
    import re
    template = frontend_text('templates/settings-model.html')
    assert 'data-zh' not in template and 'data-en' not in template
    assert 'data-i18n-placeholder="ui.model.key_placeholder"' in template
    assert '<option value="zh">' not in template
    messages = catalogs()['locales']['en']['messages']
    for key in re.findall(r'data-i18n(?:-placeholder)?="([^"]+)"', template):
        assert key in messages
