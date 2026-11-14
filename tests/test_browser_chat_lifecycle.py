"""Explicit overlapping messages keep independent request/history ordering."""
import shutil
import subprocess
from selfos.web.rendering.resources import frontend_text


def test_chat_overlap_snapshots_completion_order_and_abort_only_teardown(tmp_path):
    script=r"""
const vm=require('vm'),assert=require('assert/strict');const elements=new Map(),requests=[];let storageReads=0;
class Element{constructor(){this.value='';this.style={};this.dataset={};this.children=[];this.listeners=new Map();this.classList={add(){},remove(){},toggle(){}};}appendChild(node){node.parent=this;this.children.push(node);}remove(){if(this.parent)this.parent.children=this.parent.children.filter(child=>child!==this);}addEventListener(type,fn){this.listeners.set(type,fn);}removeEventListener(type){this.listeners.delete(type);}setAttribute(){}focus(){}querySelector(){return null;}replaceChildren(){this.children=[];}}
function element(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);}
global.window=global;global.localStorage={getItem(){storageReads++;return null;},setItem(){}};global.document={getElementById:element,querySelector:selector=>element(selector),querySelectorAll:()=>[],createElement:()=>new Element(),addEventListener(){},removeEventListener(){}};global.selfosI18n={bindText(){},t:key=>key};
global.fetch=(url,options)=>{assert.equal(url,'/chat');return new Promise(resolve=>requests.push({options,resolve}));};
RUNTIME
selfosUI.register('request',()=>({}));selfosUI.register('locale',()=>({}));
CHAT
DIMENSIONS
(async()=>{
 const chat=selfosUI.module('chat');assert.equal(storageReads,0,'Factory performed a storage read');selfosUI.init(document);assert.equal(requests.length,0);
 element('chat-input').value='typed-first';const first=chat.send();assert.equal(element('chat-input').value,'');
 element('chat-input').value='retained typed draft';const second=chat.send('dimension-second');
 assert.equal(requests.length,2);assert.deepEqual(JSON.parse(requests[0].options.body).messages,[{role:'user',content:'typed-first'}]);assert.deepEqual(JSON.parse(requests[1].options.body).messages,[{role:'user',content:'typed-first'},{role:'user',content:'dimension-second'}]);
 assert.equal(element('chat-input').value,'retained typed draft');assert(!requests[0].options.signal.aborted,'New invocation cancelled previous send');
 selfosUI.init(document);selfosUI.init(document);REPEAT
 selfosUI.init(document);assert.equal(requests.length,2);
 requests[1].resolve({ok:true,json:async()=>({reply:'second-reply'})});await second;requests[0].resolve({ok:true,json:async()=>({reply:'first-reply'})});await first;
 const third=chat.send('third');const history=JSON.parse(requests[2].options.body).messages;
 assert.deepEqual(history.map(item=>item.content),['typed-first','dimension-second','second-reply','first-reply','third']);
 const before=element('chat-messages').children.length;selfosUI.teardown();assert(requests[2].options.signal.aborted);requests[2].resolve({ok:true,json:async()=>({reply:'after-teardown'})});await third;
 assert(!chat.snapshot().history.some(item=>item.content==='after-teardown'));assert.equal(requests.length,3);assert.equal(element('chat-input').value,'retained typed draft');
 selfosUI.init(document);assert.equal(requests.length,3);assert.equal(chat.snapshot().history.length,5);
 const dims=selfosUI.module('dimensions'),card={dataset:{key:'work',score:'5',color:'blue',labelKey:'ui.dimension.work',statusKey:'status',suggKey:'sugg'}};dims.open(card);const discussion=dims.discuss();assert.equal(requests.length,4);assert.equal(element('chat-input').value,'retained typed draft');
 requests[3].resolve({ok:true,json:async()=>({reply:'dimension-reply'})});await discussion;
 selfosUI.teardown();
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    chat=frontend_text('scripts/dashboard-chat.js')
    script=script.replace('RUNTIME',frontend_text('scripts/ui-runtime.js')).replace('CHAT',chat).replace('DIMENSIONS',frontend_text('scripts/dashboard-dimensions.js')).replace('REPEAT','vm.runInThisContext('+repr(chat)+');')
    path=tmp_path/'chat.js';path.write_text(script,encoding='utf-8')
    result=subprocess.run([shutil.which('node'),str(path)],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stderr
