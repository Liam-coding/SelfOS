from html.parser import HTMLParser
from selfos.web.rendering.dashboard import generate_dashboard


def test_maintained_template_initial_text_is_keyed():
    from selfos.web.rendering.resources import frontend_text
    from selfos.web.rendering.resources import _names
    from selfos.web.i18n import catalogs
    import re
    class Inventory(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = []
        def handle_starttag(self, tag, attrs):
            if tag not in ('input', 'br', 'hr', 'img', 'meta', 'link'):
                self.stack.append((tag, dict(attrs)))
        def handle_endtag(self, tag):
            if self.stack and self.stack[-1][0] == tag:
                self.stack.pop()
        def handle_data(self, text):
            if not text.strip() or any(tag in ('script', 'style') for tag, _ in self.stack):
                return
            literal = re.sub(r'@@SELFOS_VALUE:[A-Za-z_]+@@', '', text).strip()
            if literal in ('SelfOS', 'Self', 'python -m selfos auth reset', 'SelfOS ·', ': vault/ ·') or not re.search(r'[A-Za-z]', literal):
                return
            keyed = [attrs['data-i18n'] for _, attrs in self.stack if 'data-i18n' in attrs]
            assert keyed, 'Unkeyed initial UI text: ' + text
            assert keyed[-1] in catalogs()['locales']['en']['messages']
    for name in _names():
        if name.startswith('templates/') and name.endswith('.html'):
            Inventory().feed(frontend_text(name))


def test_dashboard_keys_preserve_literal_name_and_english_defaults(tmp_path):
    vault=tmp_path/'vault';vault.mkdir()
    name='<script>source()</script> "Fixture"'
    (vault/'PROFILE.md').write_text('- Preferred name: '+name,encoding='utf-8')
    page=generate_dashboard(vault,scores={'career':6}).read_text(encoding='utf-8')
    assert 'data-label-key="ui.dimension.career"' in page
    assert 'data-status-key="ui.status.ok"' in page
    assert 'data-sugg-key="ui.suggestion.career.mid"' in page
    assert 'data-i18n="ui.dashboard.greeting"' in page
    assert '<script>source()</script>' not in page
    assert 'data-label-zh=' not in page
    assert page.index('window.selfosI18n=')<page.index('function openAppSettings')
    (vault/'PROFILE.md').unlink()
    page=generate_dashboard(vault,scores={}).read_text(encoding='utf-8')
    assert 'Hello, Liam' not in page
    assert 'data-i18n="ui.dashboard.hello"' in page


def test_open_dimension_and_pending_chat_follow_language_without_resending(tmp_path):
    import shutil, subprocess
    from selfos.web.i18n import runtime
    from selfos.web.rendering.resources import frontend_text
    common=runtime().split('<script',1)[1].split('>',1)[1].split('</script>',1)[0]
    script=frontend_text('scripts/ui-runtime.js')+frontend_text('scripts/dashboard-chat.js')+frontend_text('scripts/dashboard-dimensions.js')
    harness=r"""
const elements=new Map(),listeners=new Map(),messages=[];
function element(id){if(!elements.has(id))elements.set(id,{textContent:'',isConnected:true,style:{},dataset:{},setAttribute(){},appendChild(node){messages.push(node);},classList:{add(){},remove(){},toggle(){}},addEventListener(){},remove(){this.isConnected=false;}});return elements.get(id);}
global.window=global;global.localStorage={getItem:()=>null,setItem(){}};
global.document={documentElement:{lang:'en'},getElementById:element,createElement:()=>element('msg'+messages.length),querySelectorAll:()=>[],addEventListener:(k,f)=>{if(!listeners.has(k))listeners.set(k,[]);listeners.get(k).push(f);},dispatchEvent:e=>{for(const f of listeners.get(e.type)||[])f(e);}};

let calls=0,finish;global.fetch=async()=>{calls++;return await new Promise(resolve=>finish=()=>resolve({ok:true,json:async()=>({reply:'Literal source reply'})}));};
COMMON
DIMENSIONS
(async()=>{
openDim({dataset:{key:'career',score:'6',color:'#fff',labelKey:'ui.dimension.career',statusKey:'ui.status.ok',suggKey:'ui.suggestion.career.mid'}});
if(element('dim-modal-title').textContent!=='Career')throw Error('Dimension not keyed');
selfosI18n.setLocale('zh');if(element('dim-modal-title').textContent==='Career'||calls)throw Error('Open dimension retained old language or sent chat');
chatAboutDim();if(calls!==1||selfosUI.module('chat').snapshot().history[0].content.includes('Tell me'))throw Error('Discussion generated in stale language');
selfosI18n.setLocale('en');if(messages[1].textContent!=='Thinking...'||calls!==1)throw Error('Pending chat did not translate or resent');
finish();for(let n=0;n<20;n++)await Promise.resolve();
if(messages[messages.length-1].textContent!=='Literal source reply')throw Error('Reply altered');
selfosI18n.setLocale('zh');if(messages[messages.length-1].textContent!=='Literal source reply')throw Error('Source reply translated');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    source=tmp_path/'dimension.js';source.write_text(harness.replace('COMMON',common).replace('DIMENSIONS',script),encoding='utf-8')
    result=subprocess.run([shutil.which('node'),str(source)],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stderr


def test_scores_and_controls_have_localization_contracts(tmp_path):
    import json
    from selfos.web.rendering.resources import frontend_text
    vault=tmp_path/'vault';vault.mkdir()
    page=generate_dashboard(vault,scores={'career':6,'work':7}).read_text(encoding='utf-8')
    class Scores(HTMLParser):
        values=[]
        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs)
            if attrs.get('class') in ('overall-ring-num','ring-score'):
                assert attrs.get('data-i18n')=='ui.common.value'
                self.values.append(json.loads(attrs['data-i18n-params'])['value'])
    parser=Scores();parser.feed(page)
    assert 6.5 in parser.values and 6 in parser.values
    assert 'data-i18n-aria-label="ui.chat.send"' in page
    model=frontend_text('templates/settings-model.html')
    assert 'data-i18n="ui.model.anthropic_messages"' in model
    assert 'data-i18n="ui.model.openai_compatible"' in model


def test_decimal_scores_follow_locale_in_static_and_open_modal(tmp_path):
    import json,shutil,subprocess
    from selfos.web.i18n import catalogs,runtime
    from selfos.web.rendering.resources import frontend_text
    data=catalogs();data['locales']['fr-test']={'name':'Test French','tag':'fr-FR','document_tag':'fr','aliases':[],'messages':{}}
    common=runtime(data).split('<script',1)[1].split('>',1)[1].split('</script>',1)[0]
    script=frontend_text('scripts/ui-runtime.js')+frontend_text('scripts/dashboard-dimensions.js')
    harness=r"""
const elements=new Map();function get(id){if(!elements.has(id))elements.set(id,{textContent:'',dataset:{},isConnected:true,style:{},classList:{add(){},remove(){}},addEventListener(){}});return elements.get(id);}
const score=get('overall');score.dataset={i18n:'ui.common.value',i18nParams:'{"value":6.5}'};
global.window=global;global.localStorage={getItem:()=> 'fr-test',setItem(){}};global.document={documentElement:{lang:'en'},getElementById:get,querySelectorAll:()=>[score],addEventListener(){},dispatchEvent(){}};
COMMON
DIMENSIONS
selfosI18n.translate();if(score.textContent!=='6,5')throw Error('Static decimal score not localized');
openDim({dataset:{key:'career',score:'6.5',color:'#fff',labelKey:'ui.dimension.career',statusKey:'ui.status.ok',suggKey:'ui.suggestion.career.mid'}});
if(get('dim-modal-score').textContent!=='6,5')throw Error('Modal decimal score not localized');
selfosI18n.setLocale('en');if(get('dim-modal-score').textContent!=='6.5'||score.textContent!=='6.5')throw Error('Score switch lost numeric value');
"""
    path=tmp_path/'scores.js';path.write_text(harness.replace('COMMON',common).replace('DIMENSIONS',script),encoding='utf-8')
    result=subprocess.run([shutil.which('node'),str(path)],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stderr
