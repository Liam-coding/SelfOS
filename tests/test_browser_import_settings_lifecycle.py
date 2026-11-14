import shutil
import subprocess
import pytest

from selfos.web.rendering.resources import frontend_text


@pytest.mark.parametrize("replace_root",[False,True])
def test_teardown_pending_settings_read_restores_enabled_draft_on_remount(tmp_path,replace_root):
    script=r"""
const elements=new Map();
class Element{
 constructor(){this.value='draft';this.disabled=false;this.open=false;this.dataset={};this.children=[];this.listeners=new Map();this.style={};}
 addEventListener(type,fn){this.listeners.set(type,fn);}removeEventListener(type){this.listeners.delete(type);}
 showModal(){this.open=true;}close(){this.open=false;this.listeners.get('close')?.();}
 append(...children){this.children.push(...children);}replaceChildren(...children){this.children=children;}
 querySelectorAll(selector){if(selector==='input,select,button')return ['knowledge-custom','knowledge-detail','knowledge-save','knowledge-undo'].map(element);return [];}
}
function element(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);}
global.window=global;global.document={getElementById:element,querySelector:()=>null,querySelectorAll:()=>[],createElement:()=>new Element(),addEventListener(){},removeEventListener(){}};
global.selfosI18n={bindText(){}};let signal,reads=0;
global.fetch=(url,options)=>{reads++;if(reads>1)return Promise.resolve({ok:true,json:async()=>({settings:{domains:['draft'],detail:'draft'}})});return new Promise((resolve,reject)=>{signal=options.signal;signal.addEventListener('abort',()=>reject(Error('aborted')));});};
RUNTIME
for(const owner of ['jobs','usage','publication','request','locale'])selfosUI.register(owner,()=>({subscribe(){return ()=>{};},render(){}}));
OWNER
(async()=>{
 selfosUI.init(document);const settings=selfosUI.module('import-settings'),opening=settings.open();
 if(!element('knowledge-custom').disabled)throw Error('Opening must freeze pending settings controls');
 selfosUI.teardown();if(!signal.aborted)throw Error('Pending settings read not aborted');await opening;
 if(REPLACE_ROOT){const replacement=new Element();replacement.open=true;elements.set('knowledge-settings',replacement);}
 selfosUI.init(document);for(let n=0;n<20;n++)await Promise.resolve();if(reads!==2)throw Error('Interrupted settings read was not resumed exactly once');
 if(!element('knowledge-settings').open||element('knowledge-custom').value!=='draft')throw Error('Open draft not restored');
 if(element('knowledge-custom').disabled||element('knowledge-save').disabled)throw Error('Pending read left remounted form frozen');
 if(!element('knowledge-undo').disabled)throw Error('Missing backup incorrectly permits undo');
 const posted=[];global.fetch=async(url,options)=>{posted.push(JSON.parse(options.body));return {ok:true,json:async()=>({})};};
 for(const [input,expected]of [['research,fitness',['research','fitness']],['research，fitness',['research','fitness']],['why?fitness',['why?fitness']]]){element('knowledge-custom').value=input;await settings.save();if(JSON.stringify(posted.at(-1).domains)!==JSON.stringify(expected))throw Error('Custom domain separator changed: '+input);}
 selfosUI.teardown();
})().catch(error=>{console.error(error);process.exitCode=1;});
""".replace('RUNTIME',frontend_text('scripts/ui-runtime.js')).replace('OWNER',frontend_text('scripts/import-controls.js')).replace('REPLACE_ROOT',str(replace_root).lower())
    path=tmp_path/'pending.js';path.write_text(script,encoding='utf-8')
    result=subprocess.run([shutil.which('node'),str(path)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
