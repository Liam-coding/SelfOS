import shutil
import subprocess

from selfos.web.rendering.resources import frontend_text


def test_completion_owners_abort_reads_and_subscribe_once(tmp_path):
    script = r'''
const vm=require('vm');
const elements=new Map();
function element(id){if(!elements.has(id))elements.set(id,{textContent:'',isConnected:true,classList:{add(){},remove(){}},replaceChildren(){},addEventListener(){},removeEventListener(){}});return elements.get(id);}
global.window=global;global.document={getElementById:element,querySelector:element,addEventListener(){},removeEventListener(){},createElement:()=>element(Math.random())};
global.selfosI18n={bindText(){},t:key=>key,number:String};
let listeners=new Set(),calls=[];
global.fetch=(url,options)=>new Promise((resolve,reject)=>{calls.push({url,options,resolve,reject});options.signal.addEventListener('abort',()=>reject(new Error('aborted')));});
RUNTIME
selfosUI.register('locale',()=>({}));selfosUI.register('request',()=>({}));for(const owner of ['knowledge','import-settings','publication'])selfosUI.register(owner,()=>({}));
selfosUI.register('jobs',()=>({subscribe(fn){listeners.add(fn);return ()=>listeners.delete(fn);}}));
OWNERS
(async()=>{
 selfosUI.init(document);selfosUI.init(document);
 if(calls.length!==2||listeners.size!==2)throw Error('duplicate startup/subscription');
 for(const callback of listeners)callback({kind:'harvest',event:'finished',running:false});
 if(calls.length!==2)throw Error('Harvest updated knowledge metadata');
 selfosUI.teardown();
 if(listeners.size||calls.some(call=>!call.options.signal.aborted))throw Error('owner leaked read/subscription');
 await new Promise(resolve=>setImmediate(resolve));
 selfosUI.init(document);
 if(calls.length!==4||listeners.size!==2)throw Error('remount did not read once');
 for(const callback of listeners)callback({kind:'knowledge',event:'finished',running:false});
 if(calls.length!==4)throw Error('completion duplicated active reads');
 selfosUI.teardown();
})().catch(error=>{console.error(error);process.exitCode=1;});
'''.replace('RUNTIME', frontend_text('scripts/ui-runtime.js')).replace(
        'OWNERS', frontend_text('scripts/knowledge-quality.js') + frontend_text('scripts/overview.js'))
    path = tmp_path / 'completion.js'
    path.write_text(script, encoding='utf-8')
    result = subprocess.run([shutil.which('node'), str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_sparklines_draw_once_per_mount_and_never_at_registration(tmp_path):
    script=r"""
const vm=require('vm'),assert=require('assert/strict');let draws=0;
const canvas={dataset:{values:'[1,3,4]',color:'blue'},width:80,height:30,getContext:()=>({clearRect(){},beginPath(){},moveTo(){},lineTo(){},stroke(){draws++;}})};
global.window=global;global.document={querySelectorAll:()=>[canvas],querySelector:()=>canvas};
RUNTIME
SOURCE
assert.equal(draws,0,'Canvas drew while registering');selfosUI.init(document);selfosUI.init(document);assert.equal(draws,1);REPEAT
selfosUI.init(document);assert.equal(draws,1);selfosUI.teardown();selfosUI.init(document);assert.equal(draws,2);
"""
    import json
    source=frontend_text('scripts/dashboard-sparklines.js')
    script=script.replace('RUNTIME',frontend_text('scripts/ui-runtime.js')).replace('SOURCE',source).replace('REPEAT','vm.runInThisContext('+json.dumps(source)+');')
    path=tmp_path/'sparklines.js';path.write_text(script,encoding='utf-8')
    result=subprocess.run([shutil.which('node'),str(path)],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stderr
