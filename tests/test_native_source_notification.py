"""Native source edits notify the source editor without shared lexical state."""
import json
import shutil
import subprocess

import pytest

from selfos.web.rendering.resources import frontend_text


@pytest.mark.parametrize('action', ['checkbox', 'path', 'project-exclusions'])
def test_native_source_edits_notify_a_private_source_editor(tmp_path, action):
    script = frontend_text('scripts/opencode.js')
    harness = r'''
const assert=require('assert/strict');
class Element extends EventTarget {
  constructor(){super();this.children=[];this.dataset={};this.style={};this.value='';this.checked=false;}
  append(...children){this.children.push(...children)}
  replaceChildren(...children){this.children=children}
  before(){}
  close(){}
}
const nodes=new Map();
const get=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id)};
global.window=global;
global.document=new EventTarget();
Object.assign(document,{readyState:'complete',getElementById:get,createElement:()=>new Element()});
global.selfosI18n={t:key=>key,has:()=>true};
global.fetch=()=>{throw Error('Source editing must not start model or import requests')};
const editor=(()=>{let dirty=false;get('onboarding-roots').addEventListener('input',()=>{dirty=true});return {hasDraft:()=>dirty}})();
SOURCE
selfosHarness.update({version:2,entries:[],project_exclusions:[]},[{kind:'opencode_database',path:'C:/synthetic/opencode.db',available:true}],false);
assert.equal(editor.hasDraft(),false);
const action=ACTION;
if(action==='checkbox'){
  const checkbox=get('native-entries').children[0].children[0].children[0];
  checkbox.checked=true;checkbox.dispatchEvent(new Event('change'));
  assert.deepEqual(selfosHarness.entries(),[{kind:'opencode_database',path:'C:/synthetic/opencode.db'}]);
} else if(action==='path'){
  get('native-path').value='C:/synthetic/another.db';get('native-add').dispatchEvent(new Event('click'));
  assert.deepEqual(selfosHarness.entries(),[{kind:'opencode_database',path:'C:/synthetic/another.db'}]);
} else {
  get('onboarding-project-exclusions').value='synthetic-project';
  get('onboarding-project-exclusions').dispatchEvent(new Event('input'));
}
assert.equal(editor.hasDraft(),true,'Native selection did not notify the private source editor');
assert.equal(Object.hasOwn(global,'onboardingSourcesDirty'),false,'Source editing leaked a shared dirty flag');
'''
    source = tmp_path / 'native-source.js'
    source.write_text(harness.replace('SOURCE', script).replace('ACTION', json.dumps(action)), encoding='utf-8')
    result = subprocess.run([shutil.which('node'), str(source)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
