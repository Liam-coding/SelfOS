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


def test_publication_ui_executes_and_only_explicit_action_starts_import(tmp_path):
    module = component()
    node = shutil.which('node')
    assert node, 'Node is required for this JavaScript regression'
    fixture = {'counts': {'preferences': 0}, 'saved_checkpoints': 1234,
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
 addEventListener(type,callback){this[type]=callback;}
 setAttribute(k,v){if(k==='data-action')this.tag=v;}
}
const events=new Map();global.localStorage={getItem:()=>null,setItem(){}};global.document={documentElement:{lang:'en'},querySelectorAll:()=>[],dispatchEvent:e=>events.get(e.type)?.(),
 getElementById(id){if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);},
 createElement(){return new Element();}, addEventListener(k,f){events.set(k,f);}};
global.window=global;
let calls=[];
global.fetch=async()=>({ok:true,json:async()=>(FIXTURE)});
SCRIPT
(async()=>{global.fetch=async()=>{throw Error('offline');};await refreshImportPublication();if(!document.getElementById('import-published').textContent.includes('unavailable'))throw Error('loading must become an error');renderImportPublication(FIXTURE);
if(!document.getElementById('import-checkpoints').textContent.includes('1,234'))throw Error('Checkpoint count is not locale formatted');
if(!document.getElementById('import-modal-boundary').textContent.includes('1,234'))throw Error('Modal checkpoint count is not locale formatted');
const englishBoundary=document.getElementById('import-boundary').textContent;
if(!document.getElementById('import-published').textContent.includes('Preferences: 0'))throw Error('published count');
if(!document.getElementById('import-modal-published').textContent.includes('Preferences: 0'))throw Error('modal count');
const row=document.getElementById('import-operations').children[0];
if(!row.children.some(e=>e.textContent.includes('Preferences: 1')))throw Error('staged count');
if(calls.length)throw Error('automatic import');
const button=row.children.find(e=>e.tag==='resume');
if(!button)throw Error('resume action missing');
button.click();
if(JSON.stringify(calls)!==JSON.stringify([[false,true,false]]))throw Error('wrong import action');
selfosI18n.setLocale('zh');if(document.getElementById('import-operations').children[0]!==row)throw Error('Language switch replaced publication DOM');
if(document.getElementById('import-boundary').textContent===englishBoundary)throw Error('Publication explanation did not translate');
if(!document.getElementById('import-published').textContent.includes('偏好'))throw Error('language change');
console.log('publication UI passed');
 selfosI18n.setLocale('en');
 global.fetch=async()=>{throw Error('offline');};
 await refreshImportPublication();
 if(!document.getElementById('import-published').textContent.includes('Preferences: 0'))throw Error('refresh failure removed published metadata');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    from selfos.web.i18n import runtime
    from selfos.web.rendering.resources import frontend_text
    common=runtime().split('<script',1)[1].split('>',1)[1].split('</script>',1)[0]
    harness = harness.replace('FIXTURE', json.dumps(fixture)).replace('SCRIPT', common + frontend_text('scripts/ui-runtime.js') + "selfosUI.register('jobs',()=>({start:(...args)=>calls.push(args)}));selfosUI.register('import-settings',()=>({close(){}}));" + module.SCRIPT)
    path=tmp_path/'publication.js';path.write_text(harness,encoding='utf-8')
    result = subprocess.run([node, str(path)], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr


def test_component_is_in_refreshable_controls_and_uses_packaged_locales():
    module = component()
    from selfos.web.rendering.knowledge import CONTROLS, refresh_controls
    assert 'id="import-publication"' in CONTROLS
    assert 'refreshImportPublication' in CONTROLS
    assert refresh_controls(CONTROLS) == CONTROLS
    assert 'Published knowledge' in module.LOCALES['en'].values()
    assert module.LOCALES['en'].keys() == module.LOCALES['zh'].keys()
