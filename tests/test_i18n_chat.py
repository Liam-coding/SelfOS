import shutil,subprocess
import pytest
from selfos.web.i18n import runtime
from selfos.web.rendering.resources import frontend_text


@pytest.mark.parametrize('script_name',['dashboard-chat.js','dashboard-dimensions.js'])
@pytest.mark.parametrize('http_ok',[False,True])
def test_json_chat_errors_remain_visible_and_translate(tmp_path,script_name,http_ok):
    common=runtime().split('<script',1)[1].split('>',1)[1].split('</script>',1)[0]
    script=frontend_text('scripts/'+script_name)
    helper="""let chatCollapsed=false;const chatHistory=[];function appendMsg(text,role){const element=document.createElement('div');element.textContent=text;document.getElementById('chat-messages').appendChild(element);return element;}function toggleChat(){}""" if script_name=='dashboard-dimensions.js' else ''
    action="await _sendChatSilent('Fixture question');" if helper else "get('chat-input').value='Fixture question';await sendChat();"
    harness=r"""
const elements=new Map();
class Element{
 constructor(){this.children=[];this.textContent='';this.dataset={};this.style={};this.isConnected=true;this.value='';this.classList={add(){},toggle(){},remove(){}};}
 appendChild(child){child.parent=this;this.children.push(child);}remove(){this.isConnected=false;this.parent.children=this.parent.children.filter(child=>child!==this);}addEventListener(){}setAttribute(){}focus(){}
}
function get(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);}
global.window=global;global.localStorage={getItem:()=>null,setItem(){}};global.document={documentElement:{lang:'en'},getElementById:get,createElement:()=>new Element(),querySelectorAll:()=>[],addEventListener(){},dispatchEvent(){}};
global.fetch=async()=>({ok:HTTP_OK,json:async()=>({error:'RAW PRIVATE PROVIDER ERROR'})});
COMMON
HELPER
SCRIPT
(async()=>{
ACTION
const messages=get('chat-messages').children,failure=messages[messages.length-1];
if(messages.length!==2||!failure.isConnected||!failure.textContent.includes('Connection failed'))throw Error('JSON failure has no visible error message');
selfosI18n.setLocale('zh');if(failure.textContent.includes('Connection failed')||failure.textContent.includes('RAW PRIVATE'))throw Error('Visible failure did not translate safely');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    source=tmp_path/'chat.js';source.write_text(harness.replace('HTTP_OK','true' if http_ok else 'false').replace('COMMON',common).replace('HELPER',helper).replace('SCRIPT',script).replace('ACTION',action),encoding='utf-8')
    result=subprocess.run([shutil.which('node'),str(source)],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stderr
