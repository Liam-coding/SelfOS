import importlib
import json
import shutil
import subprocess

import pytest


def component():
    try:
        return importlib.import_module('selfos.web.rendering.import_status')
    except ModuleNotFoundError:
        pytest.fail('Publication status UI is not implemented')


def test_publication_ui_executes_and_only_explicit_action_starts_import():
    module = component()
    node = shutil.which('node')
    assert node, 'Node is required for this JavaScript regression'
    fixture = {'counts': {'preferences': 0}, 'saved_checkpoints': 1,
               'publication': {'diagnostics': 0, 'operations': [
                   {'id': 'example', 'status': 'stopped', 'phase': 'extracting',
                    'compatible': True, 'resume_eligible': True, 'staged_counts': {'preferences': 1},
                    'staged_snapshot_published': False, 'saved_sessions': 1}]}}
    harness = r'''
const nodes = new Map();
class Element {
 constructor(){this.children=[];this.textContent='';this.hidden=false;}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=items;}
 addEventListener(){}
 setAttribute(k,v){if(k==='data-action')this.tag=v;}
}
global.document={documentElement:{lang:'en'},
 getElementById(id){if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);},
 createElement(){return new Element();}, addEventListener(){}};
global.window=global;
let calls=[];global.confirmHarvest=(...args)=>calls.push(args);
global.fetch=async()=>({ok:true,json:async()=>(FIXTURE)});
SCRIPT
renderImportPublication(FIXTURE);
if(!document.getElementById('import-published').textContent.includes('Preferences: 0'))throw Error('published count');
if(!document.getElementById('import-modal-published').textContent.includes('Preferences: 0'))throw Error('modal count');
const row=document.getElementById('import-operations').children[0];
if(!row.children.some(e=>e.textContent.includes('Preferences: 1')))throw Error('staged count');
if(calls.length)throw Error('automatic import');
const button=row.children.find(e=>e.tag==='resume');
if(!button)throw Error('resume action missing');
button.onclick();
if(JSON.stringify(calls)!==JSON.stringify([[false,true,false]]))throw Error('wrong import action');
document.documentElement.lang='zh';renderImportPublication(FIXTURE);
if(!document.getElementById('import-published').textContent.includes('偏好'))throw Error('language change');
console.log('publication UI passed');
(async()=>{
 importPublicationData=null;document.documentElement.lang='en';
 global.fetch=async()=>{throw Error('offline');};
 await refreshImportPublication();
 if(!document.getElementById('import-published').textContent.includes('unavailable'))throw Error('loading must become an error');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    harness = harness.replace('FIXTURE', json.dumps(fixture)).replace('SCRIPT', module.SCRIPT)
    result = subprocess.run([node, '-e', harness], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr


def test_component_is_in_refreshable_controls_and_uses_packaged_locales():
    module = component()
    from selfos.web.rendering.knowledge import CONTROLS, refresh_controls
    assert 'id="import-publication"' in CONTROLS
    assert 'refreshImportPublication' in CONTROLS
    assert refresh_controls(CONTROLS) == CONTROLS
    assert 'Published knowledge' in module.LOCALES['en'].values()
    assert module.LOCALES['en'].keys() == module.LOCALES['zh'].keys()
