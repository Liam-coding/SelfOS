"""Delayed status reads cannot replace newer user-approved setup state."""
import shutil
import subprocess

import pytest


def test_guide_keeps_current_selection_and_saves_exclusions_before_advancing(tmp_path):
    from selfos.web.rendering.resources import frontend_text
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for browser state validation')
    harness = r"""
const elements=new Map(),callbacks={};
function element(id){if(!elements.has(id))elements.set(id,{value:'',textContent:'',open:false,hidden:false,disabled:false,
  showModal(){this.open=true;},close(){this.open=false;},addEventListener(){},replaceChildren(){},append(){}});return elements.get(id);}
global.window=global;window.selfosI18n={bindText(){},t:k=>k};
global.document={getElementById:element,querySelector:()=>null,querySelectorAll:()=>[],createElement:()=>element('new'),
  addEventListener:(name,callback)=>callbacks[name]=callback};
const releases=[];global.fetch=()=>new Promise(resolve=>releases.push(data=>resolve({ok:true,json:async()=>data})));
__SCRIPT__
const data=path=>({progress:{step:0,status:'active',preview_id:null},availability:[],sources:{roots:[path],exclusions:[]},
  model:{provider:'openai',model:'synthetic'},preview:null,budget:null,knowledge:{counts:{cards:0,lessons:0,personal_facts:0,preferences:0,history:0},saved_checkpoints:0}});
(async()=>{
 callbacks.DOMContentLoaded();
 const opening=openOnboarding();
 releases[1](data('current-selection'));await opening;
 releases[0](data('stale-selection'));await new Promise(resolve=>setImmediate(resolve));
 if(element('onboarding-roots').value!=='current-selection')throw Error('Stale initial read replaced the current guide');
 onboardingData.progress.step=1;onboardingSourcesDirty=true;
 element('onboarding-roots').value='/selected-conversations';element('onboarding-exclusions').value='/selected-conversations/private';
 const posted=[];global.fetch=async(url,options)=>{const body=JSON.parse(options.body);posted.push(body);const value=data('/selected-conversations');value.progress.step=body.action==='save_step'?body.step:1;return {ok:true,json:async()=>value};};
 await onboardingStep(1);
 if(posted[0]?.action!=='save_sources'||posted[0].sources.exclusions[0]!=='/selected-conversations/private')throw Error('Next ignored unsaved privacy exclusions');
 if(posted[1]?.action!=='save_step'||posted[1].step!==2)throw Error('Next did not advance after saving sources');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    path = tmp_path / 'onboarding-state.js'
    path.write_text(harness.replace('__SCRIPT__', frontend_text('scripts/onboarding.js')), encoding='utf-8')
    result = subprocess.run([node, str(path)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
