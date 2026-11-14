import shutil
import subprocess


def test_model_form_cannot_edit_or_submit_before_saved_configuration_loads(tmp_path):
    import pytest
    from selfos.web.rendering.resources import frontend_text
    node=shutil.which('node')
    if not node:pytest.skip('Node is needed for browser script validation')
    script=frontend_text('scripts/ui-runtime.js')+frontend_text('scripts/settings-model.js')
    harness=r"""
const controls=Array.from({length:3},()=>({disabled:false})),close={disabled:false};
const elements=new Map();
function element(id){if(!elements.has(id))elements.set(id,{value:'',checked:false,open:false,showModal(){this.open=true;},close(){this.open=false;},append(){},style:{}});return elements.get(id);}
global.window=global;window.selfosI18n={bindText(){},t:k=>k};
global.document={getElementById:element,querySelector:()=>({querySelectorAll:selector=>selector.includes(':not')?controls:[...controls,close]}),addEventListener(){}};
const releases=[];global.fetch=()=>new Promise(resolve=>releases.push(model=>resolve({ok:true,json:async()=>({provider:'openai',model,base_url:'http://localhost/v1',proxy_mode:'direct',proxy_url:''})})));
__SCRIPT__
(async()=>{
 const opening=openModelSettings();
 if(!controls.every(control=>control.disabled))throw Error('Form can overwrite input while configuration is loading');
 if(close.disabled)throw Error('Close is disabled while loading');
 element('model-settings').close();const reopened=openModelSettings();
 releases[0]('stale-model');await opening;
 if(controls.some(control=>!control.disabled))throw Error('Stale response enables reopened form');
 releases[1]('saved-model');await reopened;
 if(controls.some(control=>control.disabled))throw Error('Form remains disabled after loading');
 if(element('model-name').value!=='saved-model')throw Error('Saved model not initialized');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    path=tmp_path/'model-loading.js';path.write_text(harness.replace('__SCRIPT__',script),encoding='utf-8')
    result=subprocess.run([node,str(path)],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
