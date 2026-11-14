import json
import shutil
import subprocess
from selfos.web.rendering.resources import frontend_text


def test_knowledge_family_is_inert_and_aborts_every_pending_body_on_teardown(tmp_path):
    script=r"""
const vm=require('vm'),assert=require('assert/strict'),nodes=new Map(),requests=[];let writes=0;
class Element{constructor(){this.value='';this.children=[];this.dataset={};this.style={};this.open=false;this.listeners=new Map();this.isConnected=true;}append(...children){writes++;this.children.push(...children);}replaceChildren(...children){writes++;this.children=children;}setAttribute(){writes++;}addEventListener(type,fn){this.listeners.set(type,fn);}removeEventListener(type){this.listeners.delete(type);}querySelectorAll(){return [];}querySelector(){return null;}focus(){}showModal(){this.open=true;}close(){this.open=false;this.listeners.get('close')?.();}scrollIntoView(){}}
function node(id){if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);}
global.window=global;global.document={getElementById:node,querySelector:selector=>selector.startsWith('#')?node(selector.slice(1)):null,querySelectorAll:()=>[],createElement:()=>new Element(),createTextNode:()=>new Element(),addEventListener(){},removeEventListener(){}};global.selfosI18n={has:()=>false,t:key=>key,number:String,bindText(){writes++;},date:String};global.matchMedia=()=>({matches:true});
global.fetch=(url,options)=>new Promise(resolve=>requests.push({url,options,resolve}));
RUNTIME
selfosUI.register('request',()=>({}));selfosUI.register('locale',()=>({}));
OWNERS
(async()=>{
 assert.equal(writes,0,'Factory/script wrote UI before mount');selfosUI.init(document);assert.equal(requests.length,1);
 const knowledge=selfosUI.module('knowledge'),timeline=selfosUI.module('timeline'),corrections=selfosUI.module('corrections');
 const detail=knowledge.openDetail('pending-record'),chronology=timeline.open('project'),history=corrections.history(new Element(),()=>{});assert.equal(requests.length,4);
 selfosUI.init(document);selfosUI.init(document);vm.runInThisContext(OWNERS_JSON);selfosUI.init(document);assert.equal(requests.length,4);
 selfosUI.teardown();assert(requests.every(request=>request.options.signal.aborted),'Owner leaked pending request');writes=0;
 for(const request of requests)request.resolve({ok:true,json:async()=>({items:[],total:0,actions:[],item:{},sources:[],source_count:0,current:null})});
 await Promise.all([detail,chronology,history]);for(let n=0;n<20;n++)await Promise.resolve();assert.equal(writes,0,'Stale body wrote UI after teardown');
 selfosUI.init(document);selfosUI.teardown();
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    owners=''.join(frontend_text('scripts/'+name) for name in ['knowledge-corrections.js','project-timeline.js','knowledge-browser.js'])
    script=script.replace('RUNTIME',frontend_text('scripts/ui-runtime.js')).replace('OWNERS_JSON',json.dumps(owners)).replace('OWNERS',owners)
    path=tmp_path/'knowledge.js';path.write_text(script,encoding='utf-8')
    result=subprocess.run([shutil.which('node'),str(path)],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stderr


def test_correction_edit_and_merge_drafts_survive_remount_without_mutation(tmp_path):
    script=r"""
const assert=require('assert/strict'),listeners=new Map();
class Element{constructor(tag='div'){this.tag=tag;this.children=[];this.dataset={};this.attributes={};this.value='';this.isConnected=true;}append(...nodes){for(const node of nodes){node.parent=this;this.children.push(node);}}replaceChildren(...nodes){this.children=[];this.append(...nodes);}setAttribute(key,value){this.attributes[key]=value;}removeAttribute(key){delete this.attributes[key];}querySelectorAll(selector){return descendants(this).filter(node=>selector==='button'?node.tag==='button':false);}querySelector(selector){return this.querySelectorAll(selector)[0];}focus(){}closest(selector){return selector==='[data-selfos-action]'?this:holder;}get selectedOptions(){return this.children.filter(node=>node.selected);}}
const descendants=node=>node.children.flatMap(child=>[child,...descendants(child)]),find=attribute=>descendants(holder).find(node=>Object.hasOwn(node.attributes,'data-correction-'+attribute));
const holder=new Element(),element=new Element();global.window=global;global.document={getElementById:()=>null,createElement:tag=>new Element(tag),contains:()=>true,addEventListener:(type,fn)=>listeners.set(type,fn),removeEventListener:type=>listeners.delete(type)};global.selfosI18n={t:key=>key,bindText(){}};global.crypto=require('crypto').webcrypto;let posts=[],failNext=false;global.fetch=async(url,options)=>{posts.push(JSON.parse(options.body));const ok=!failNext;failNext=false;return {ok,json:async()=>ok?{}:{code:'correction_unavailable'}};};
const event=(node,type)=>listeners.get(type)({target:node,type,preventDefault(){}}),data={item:{id:'record',category:'preferences'},corrections:{editable:true,value:'Initial value',text:'Initial text',compatible:[{id:'other',title:'Other'}]}};
RUNTIME
selfosUI.register('request',()=>({}));selfosUI.register('locale',()=>({}));
CORRECTIONS
(async()=>{
 selfosUI.init(document);const corrections=selfosUI.module('corrections');
 for(const mode of ['edit','merge']){
  holder.replaceChildren();corrections.mount(holder,data,()=>{});event(find(mode),'click');find('value').value='Dirty value';find('text').value='Dirty text';if(mode==='merge')find('candidates').children[0].selected=true;
  selfosUI.teardown();holder.replaceChildren();selfosUI.init(document);corrections.mount(holder,data,()=>{});
  assert.equal(find('value')?.value,'Dirty value');assert.equal(find('text')?.value,'Dirty text');if(mode==='merge')assert.equal(find('candidates').selectedOptions[0]?.value,'other');assert.equal(posts.length,mode==='edit'?0:1,'Remount sent mutation');
  event(descendants(holder).find(node=>node.tag==='form'),'submit');for(let n=0;n<20;n++)await Promise.resolve();assert.deepEqual(posts.at(-1).patch,{value:'Dirty value',text:'Dirty text'});assert.equal(posts.at(-1).action,mode);
 }
 holder.replaceChildren();corrections.mount(holder,data,()=>{});event(find('edit'),'click');find('text').value='Retry draft';failNext=true;event(descendants(holder).find(node=>node.tag==='form'),'submit');for(let n=0;n<20;n++)await Promise.resolve();const retryId=posts.at(-1).request_id;selfosUI.teardown();holder.replaceChildren();selfosUI.init(document);corrections.mount(holder,data,()=>{});assert.equal(posts.length,3,'Remount replayed failed mutation');event(descendants(holder).find(node=>node.tag==='form'),'submit');for(let n=0;n<20;n++)await Promise.resolve();assert.equal(posts.at(-1).request_id,retryId,'Remount reset retry identity');event(find('edit'),'click');assert.equal(find('text').value,'Initial text','Saved or canceled restore resurrected old draft');
 selfosUI.teardown();
})().catch(error=>{console.error(error);process.exitCode=1;});
""".replace('RUNTIME',frontend_text('scripts/ui-runtime.js')).replace('CORRECTIONS',frontend_text('scripts/knowledge-corrections.js'))
    path=tmp_path/'correction-drafts.js';path.write_text(script,encoding='utf-8')
    result=subprocess.run([shutil.which('node'),str(path)],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stderr
