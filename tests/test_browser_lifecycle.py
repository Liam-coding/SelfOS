"""Exercise packaged classic runtime without provider I/O."""
import shutil
import subprocess
import json
import re
from pathlib import Path


def test_packaged_bootstrap_protects_feature_readiness_requests_from_auth_expiry(tmp_path):
    from selfos.web.rendering.resources import frontend_text
    template=frontend_text('templates/dashboard-page.html')
    entries=[]
    for attrs,source in re.findall(r'<script([^>]*)>(.*?)</script>',template,re.S):
        owner=re.search('data-selfos-module="([^"]+)"',attrs)
        if owner:entries.append({'owner':owner[1],'source':source})
    payload=tmp_path/'scripts.json';payload.write_text(json.dumps(entries),encoding='utf-8')
    result=subprocess.run([shutil.which('node'),'-e',r"""
const fs=require('fs'),assert=require('assert/strict'),ready=[];
global.window=global;global.document={readyState:'loading',addEventListener(type,callback){if(type==='DOMContentLoaded')ready.push(callback)}};
global.selfosI18n={};let redirects=0,calls=0;global.location={replace(){redirects++}};
global.fetch=async()=>{calls++;return {status:401}};
for(const entry of JSON.parse(fs.readFileSync(process.argv[1],'utf8'))){
 if(['runtime','request','bootstrap'].includes(entry.owner))eval(entry.source);
 if(entry.owner==='chat')document.addEventListener('DOMContentLoaded',()=>fetch('/private-fixture'));
}
(async()=>{ready.forEach(callback=>callback());await Promise.resolve();await Promise.resolve();assert.equal(calls,1);assert.equal(redirects,1,'Auth boundary mounted after feature reads');})();
""",str(payload)],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr


def test_browser_lifecycle_preflight_repeat_delivery_and_cleanup():
    runtime = Path(__file__).parents[1] / "src/selfos/resources/web/scripts/ui-runtime.js"
    assert runtime.exists(), "Missing versioned browser lifecycle runtime"
    result = subprocess.run([shutil.which("node"), "-e", r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync(process.argv[1],'utf8'), doc={},log=[];
const ctx=vm.createContext({window:{},console});vm.runInContext(source,ctx);
const ui=ctx.window.selfosUI;
ui.register('feature',()=>({init(){log.push('feature')},teardown(){log.push('clean-feature')}}),{dependencies:['base']});
assert.throws(()=>ui.init(doc),/Missing/);assert.deepEqual(log,[]);
ui.register('base',()=>({init(){log.push('base')},teardown(){log.push('clean-base')}}));
ui.init(doc);ui.init(doc);vm.runInContext(source,ctx);
ui.register('base',()=>{throw Error('duplicate factory')});ui.init(doc);
assert.deepEqual(log,['base','feature']);assert.equal(ui,ctx.window.selfosUI);
assert.equal(ui.module('base'),ui.module('base'));
assert.throws(()=>ui.register('base',()=>({}),{version:2}),/version/i);
ui.teardown();assert.deepEqual(log,['base','feature','clean-feature','clean-base']);
ui.init(doc);assert.deepEqual(log.slice(-2),['base','feature']);ui.teardown();
const cycle=vm.createContext({window:{}});vm.runInContext(source,cycle);
cycle.window.selfosUI.register('a',()=>({}),{dependencies:['b']});
cycle.window.selfosUI.register('b',()=>({}),{dependencies:['a']});
assert.throws(()=>cycle.window.selfosUI.init(doc),/Cyclic/);
const fail=vm.createContext({window:{}});vm.runInContext(source,fail);let cleaned=0;
fail.window.selfosUI.register('first',()=>({init(){},teardown(){cleaned++}}));
fail.window.selfosUI.register('bad',()=>({init(){throw Error('mount failed')},teardown(){cleaned++}}));
assert.throws(()=>fail.window.selfosUI.init(doc),/mount failed/);assert.equal(cleaned,2);
const roots=vm.createContext({window:{}});vm.runInContext(source,roots);let node={},busy=false;
const rootedDoc={querySelector:()=>node};
roots.window.selfosUI.register('root',()=>({busy:()=>busy}),{roots:['#root']});roots.window.selfosUI.init(rootedDoc);
node={};assert.throws(()=>roots.window.selfosUI.init(rootedDoc),/remount-required/);
busy=true;assert.throws(()=>roots.window.selfosUI.init(rootedDoc),/busy/);
""", str(runtime)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_account_repeated_delivery_wraps_fetch_once_and_teardown_restores_boundary():
    scripts = Path(__file__).parents[1] / "src/selfos/resources/web/scripts"
    assert (scripts/'ui-request.js').exists(), 'Missing shared auth request owner'
    result = subprocess.run([shutil.which("node"), "-e", r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
let calls=0,redirects=0,translated=0,release;const native=async path=>{calls++;if(path==='/slow')return await new Promise(resolve=>release=()=>resolve({status:401}));return {status:401}};
const window={fetch:native};const document={getElementById:()=>null,addEventListener(){},removeEventListener(){}};
const ctx=vm.createContext({window,document,location:{replace(){redirects++}},authRequest(){},translateAuth(){translated++}});
vm.runInContext(fs.readFileSync(process.argv[1]+'/ui-runtime.js','utf8'),ctx);
window.selfosUI.register('locale',()=>({}));window.selfosUI.register('auth',()=>({translate(){translated++;}}));
vm.runInContext(fs.readFileSync(process.argv[1]+'/ui-request.js','utf8'),ctx);
const source=fs.readFileSync(process.argv[1]+'/account.js','utf8');
vm.runInContext(source,ctx);assert.equal(window.fetch,native);
window.selfosUI.init(document);const wrapped=window.fetch;
vm.runInContext(source,ctx);window.selfosUI.init(document);assert.equal(window.fetch,wrapped);
(async()=>{await window.fetch('/private');assert.equal(calls,1);assert.equal(redirects,1);
await window.fetch('/auth/status');assert.equal(redirects,1);assert.equal(translated,1);
const delayed=window.fetch('/slow');window.selfosUI.teardown();assert.equal(window.fetch,native);release();await delayed;assert.equal(redirects,1);})();
""", str(scripts)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_theme_registration_is_inert_and_reinitialization_preserves_theme():
    scripts = Path(__file__).parents[1] / "src/selfos/resources/web/scripts"
    result = subprocess.run([shutil.which("node"), "-e", r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
let changes=0,translations=0,listeners=0;const nodes={};
const doc={getElementById:id=>nodes[id]||(nodes[id]={textContent:'',dataset:{}}),body:{classList:{add(){changes++},toggle(){changes++}}},addEventListener(){listeners++},removeEventListener(){listeners--}};
const window={selfosI18n:{locale:'en',documentTag:'en',locales:{en:{},zh:{}},translate(){translations++},setLocale(){}}};
const ctx=vm.createContext({window,document:doc,localStorage:{getItem:()=>null,setItem(){}}});
vm.runInContext(fs.readFileSync(process.argv[1]+'/ui-runtime.js','utf8'),ctx);
window.selfosUI.register('locale',()=>window.selfosI18n);
const source=fs.readFileSync(process.argv[1]+'/dashboard-theme-language.js','utf8');
vm.runInContext(source,ctx);assert.equal(changes,0);assert.equal(translations,0);
window.selfosUI.init(doc);window.selfosUI.module('theme').toggle();
const before=changes,translated=translations;vm.runInContext(source,ctx);window.selfosUI.init(doc);window.selfosUI.init(doc);
assert.equal(changes,before);assert.equal(translations,translated);assert.equal(listeners,2);
window.selfosUI.teardown();assert.equal(listeners,0);
""", str(scripts)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
