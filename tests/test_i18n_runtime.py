import shutil
import subprocess


def test_actual_runtime_translates_static_dynamic_and_preserves_input_values(tmp_path):
    from selfos.web.i18n import runtime
    script = runtime().split('<script', 1)[1].split('>', 1)[1].split('</script>', 1)[0]
    harness = r"""
const entries=new Map(),events=[],storage=new Map([['selfos-lang','unsupported']]);
class Element {
 constructor(){this.dataset={};this.value='unsaved';this._text='';this.attributes={};this.children=[];this.isConnected=true;}
 set textContent(v){this._text=String(v);}get textContent(){return this._text;}
 set innerHTML(v){throw Error('Unsafe HTML');}setAttribute(k,v){this.attributes[k]=v;}
 append(child){this.children.push(child);}replaceChildren(...v){this.children=v;}getAttribute(k){return this.attributes[k]??null;}
}
const status=new Element(),input=new Element(),staticText=new Element();
staticText.dataset.i18n='ui.common.greeting';staticText.dataset.i18nParams=JSON.stringify({name:'<Fixture>'});
global.document={documentElement:{lang:''},querySelectorAll(){return [staticText];},getElementById(id){if(id==='status')return status;return null;},createElement(){return new Element();},addEventListener(type,fn){events.push([type,fn]);},dispatchEvent(){}};
global.window=global;global.localStorage={getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)};
SCRIPT
const i=window.selfosI18n;
if(i.locale!=='en'||document.documentElement.lang!=='en')throw Error('English default/fallback required');
i.translate();if(staticText.textContent!=='Hello, <Fixture>')throw Error('Safe static text failed');
i.bindText(status,'ui.common.count',{count:1234});
if(!status.textContent.includes('1,234'))throw Error('Locale number parameters failed');
const englishDate=i.date('2026-01-02');
if(i.date('2026-01-02',{timeStyle:'short',timeZone:'America/Los_Angeles'})!==englishDate)throw Error('Date-only value acquired time or shifted calendar day');
if(i.date('2026-02-29')!==i.t('ui.common.unknown'))throw Error('Non-leap calendar date accepted');
if(i.date('2024-02-29')===i.t('ui.common.unknown'))throw Error('Valid leap date rejected');
let missingRejected=false;try{i.t('ui.common.greeting',Object.create({name:'Inherited'}));}catch(error){missingRejected=true;}
if(!missingRejected)throw Error('Inherited parameter accepted');

i.setLocale('zh');
if(i.locale!=='zh-CN'||storage.get('selfos-lang')!=='zh-CN')throw Error('Legacy preference resolution failed');
if(!status.textContent.includes('条')||input.value!=='unsaved')throw Error('Dynamic translation disturbed state');
if(i.date('2026-01-02')===englishDate||i.date('ambiguous')!==i.t('ui.common.unknown'))throw Error('Date formatting failed');
i.setLocale('missing');if(i.locale!=='en')throw Error('Unsupported locale fallback failed');
if(i.date('2026-02-30T08:00:00Z')!==i.t('ui.common.unknown'))throw Error('Invalid recorded calendar date was normalized');
i.bindText(status,'ui.common.greeting',()=>({name:i.t('ui.common.unknown')}));
if(status.textContent!=='Hello, Unknown')throw Error('Derived parameter binding failed');
i.setLocale('zh');if(status.textContent!=='你好，未知')throw Error('Derived parameter retained the previous language');
const malformed=new Element();malformed.dataset.i18n='ui.common.greeting';malformed.dataset.i18nParams='null';
document.querySelectorAll=()=>[malformed,staticText];
i.translate();if(staticText.textContent!=='\u4f60\u597d\uff0c<Fixture>')throw Error('Malformed element stopped unrelated translations');
let broken=true;i.bindText(status,'ui.common.greeting',()=>{if(broken)throw Error('fixture invalid params');return {name:'Recovered'};});
broken=false;i.setLocale('en');if(status.textContent!=='Hello, Recovered')throw Error('Failed binding could not recover');
"""
    node = shutil.which('node')
    assert node
    source = tmp_path / 'runtime.js'
    source.write_text(harness.replace('SCRIPT', script), encoding='utf-8')
    result = subprocess.run([node, str(source)], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr


def test_resource_only_locale_uses_metadata_selector_and_english_fallback(tmp_path):
    from selfos.web.i18n import catalogs, runtime
    data=catalogs()
    data['locales']['x-test']={'name':'Test locale','tag':'en-GB','document_tag':'x-test','aliases':['xt'],'messages':{'ui.common.unknown':'Test unknown'}}
    script=runtime(data).split('<script',1)[1].split('>',1)[1].split('</script>',1)[0]
    harness=r"""
const select={children:[],value:'',replaceChildren(){this.children=[];},append(child){this.children.push(child);}};
global.window=global;global.localStorage={getItem:()=> 'xt',setItem(){}};global.document={documentElement:{lang:'en'},querySelectorAll:()=>[],getElementById:()=>select,createElement:()=>({}),addEventListener(){},dispatchEvent(){}};
SCRIPT
const i=selfosI18n;i.populateLanguageSelect(select);
if(i.locale!=='x-test'||select.value!=='x-test'||select.children.length!==3||select.children[2].textContent!=='Test locale')throw Error('Locale metadata not discovered');
if(i.t('ui.common.unknown')!=='Test unknown'||i.t('ui.common.greeting',{name:'Fixture'})!=='Hello, Fixture')throw Error('Missing translation fallback failed');
if(i.date('2026-01-02')!=='2 Jan 2026')throw Error('Metadata Intl locale not used');
const NativeNumber=Intl.NumberFormat,NativeDate=Intl.DateTimeFormat;
Intl.NumberFormat=function(tag,options){if(tag==='en-GB')throw new RangeError('Fixture unsupported formatter');return new NativeNumber(tag,options);};
Intl.DateTimeFormat=function(tag,options){if(tag==='en-GB')throw new RangeError('Fixture unsupported formatter');return new NativeDate(tag,options);};
if(i.number(1234)!=='1,234'||i.date('2026-01-02')!=='Jan 2, 2026')throw Error('Formatter fallback failed');
i.setLocale('unsupported');if(i.locale!=='en')throw Error('Unsupported preference failed');
"""
    source=tmp_path/'locale.js';source.write_text(harness.replace('SCRIPT',script),encoding='utf-8')
    result=subprocess.run([shutil.which('node'),str(source)],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stderr
