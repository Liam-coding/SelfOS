"""All owners and actual native controls on refreshed, loopback-only pages."""
import json
import re
import threading
import socket
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer as BaseThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
from chromium_fixture import run_chromium


class ThreadingHTTPServer(BaseThreadingHTTPServer):
    # Reinitialization reconnects multiple owners while aborted sockets drain.
    request_queue_size=64


def test_fixture_accepts_remount_connection_burst_before_dispatch():
    """A remount may reconnect several owners while canceled reads are draining."""
    server=ThreadingHTTPServer(('127.0.0.1',0),BaseHTTPRequestHandler)
    connections=[]
    try:
        for _ in range(24):
            connections.append(socket.create_connection(server.server_address,timeout=0.25))
    finally:
        for connection in connections:connection.close()
        server.server_close()


@pytest.fixture
def interfaces_server(tmp_path,request):
    from selfos.web.rendering.dashboard import generate_dashboard
    from selfos.web.rendering.refresh import refresh_dashboard
    from selfos.web.rendering.auth import login_page
    vault=tmp_path/'vault';vault.mkdir()
    (vault/'PROFILE.md').write_text('- Preferred name: Fixture',encoding='utf-8')
    page=generate_dashboard(vault,scores={'career':7,'work':6}).read_text(encoding='utf-8')
    if getattr(request,'param','current')=='pre45':
        page=re.sub(r'<script[^>]*data-selfos-module="[^"]+"[^>]*>.*?</script>','',page,flags=re.S)
        page=page.replace('data-selfos-action="chat.toggle"','onclick="toggleChat()"').replace('id="chat-collapse-btn" onclick="toggleChat()"','id="chat-collapse-btn" onclick="toggleChat(event)"').replace('data-selfos-action="chat.send"','onclick="sendChat()"').replace('data-selfos-action="dimensions.open"','onclick="openDim(this)"').replace('data-selfos-action="dimensions.discuss"','onclick="chatAboutDim()"')
        page=page.replace('</body>','<script>let isDark=false;window.legacyCounterpart=true;</script></body>')
    custom='<script data-selfos-module="custom">window.customKept=true;const marker=\'data-selfos-module="theme"\';</script><button id="custom-control" data-selfos-action="unknown.custom">Fixture control</button>'
    page=page.replace('</body>',custom+'</body>')
    owners=['runtime','request','bootstrap','auth','account','settings','theme','jobs','import-settings','usage','publication','quality','overview','staging','onboarding','chat','dimensions','privacy','sparklines','knowledge','corrections','timeline']
    for _ in range(3):
        page=refresh_dashboard(page)
        for owner in owners:assert page.count('<script data-selfos-module="'+owner+'"')==1,owner
        assert custom in page
        assert 'window.legacyCounterpart=true' not in page
    instrument='<script>window.pageErrors=[];window.requestRecords=[];window.addEventListener("error",e=>pageErrors.push(e.message));const fixtureFetch=window.fetch;window.fetch=(url,options={})=>{requestRecords.push({url:String(url),signal:options.signal,body:options.body});return fixtureFetch(url,options);};</script>'
    pages={'/':page.replace('</head>',instrument+'</head>').encode(),'/login':login_page().replace('</head>',instrument+'</head>').encode()}
    counts=Counter();posts=[];queries=[];release=threading.Event();release.set();state={'auth':'setup','hold':False}
    item={'id':'project1','category':'projects','title':'Fixture project','summary':'Initial project context','status':'in_progress','date':'2026-01-02','source_count':1,'decisions':['Literal decision'],'blockers':['Literal blocker'],'next_steps':['Literal next step'],'source_scope':'session_context'}
    source={'id':'source1','source':'codex','role':'user','timestamp':'2026-01-02T08:00:00Z','file':'synthetic.jsonl'}
    detail={'item':item,'sources':[source],'source_count':1,'corrections':{'editable':True,'text':'Initial project context','compatible':[{'id':'project2','title':'Other project'}]}}
    usage={'budget':{'max_requests':100},'runs':[]}
    settings={'settings':{'domains':['work'],'detail':'balanced'},'counts':{'cards':1},'saved_checkpoints':2,'publication':{'operations':[]},'usage':usage}
    model={'provider':'openai','model':'fixture-model','base_url':'http://fixture.invalid','has_api_key':False,'proxy_source':'direct','effective_proxy':{},'proxy_mode':'direct','proxy_url':''}
    guide={'progress':{'step':1,'status':'active'},'availability':[],'sources':{'roots':['C:/synthetic'],'exclusions':[]},'model':{'provider':'openai','model':'fixture'},'preview':None,'budget':None,'knowledge':{'counts':{'cards':1},'saved_checkpoints':2}}
    privacy={'selection':{'roots':['C:/synthetic'],'exclusions':[],'privacy_exclusions':[]},'destination':{'model':'Fixture model'},'withheld_sources':0}
    milestone={'id':'milestone1','type':'goals','text':'Literal milestone','status':'','blockers':[],'next_steps':[],'event_time':'','observed_at':'2026-01-02','source_times':[],'imported_at':'','ordering_basis':'observation','source_scope':'session_context','superseded':False,'sources':[source],'unavailable_source_count':0}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def respond(self,data,status=200,kind='application/json'):
            payload=data if isinstance(data,bytes) else json.dumps(data).encode()
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(payload)));self.end_headers()
            try:self.wfile.write(payload)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
        def do_GET(self):
            url=urlsplit(self.path);path=url.path;query=parse_qs(url.query);counts[path]+=1;queries.append((path,query))
            if path in pages:return self.respond(pages[path],kind='text/html; charset=utf-8')
            if path=='/fixture-stats':return self.respond({'counts':dict(counts),'posts':posts,'queries':queries})
            if path=='/auth/status':return self.respond({'authenticated':False,'state':state['auth']})
            if path=='/__knowledge__':return self.respond({'items':[item],'total':1,'filtered_counts':{'projects':1},'filters':{'projects':[],'sources':['codex']}})
            if path=='/__knowledge_item__':
                if state['hold']:release.wait(10)
                return self.respond(detail)
            if path=='/__knowledge_source__':
                offset=int(query.get('offset',['0'])[0]);text='Literal original <source>'.ljust(24000,'x') if offset==0 else ' retained tail'
                return self.respond({'text':text,'text_total':24014,'next_offset':24000 if offset==0 else None})
            if path=='/__knowledge_timeline__':return self.respond({'revision':'a'*64,'current':{'title':'Fixture project','intent':'Current fixture goal','status':'blocked','blockers':['Literal blocker'],'decisions':[],'next_steps':[]},'items':[dict(milestone,id='milestone'+query.get('offset',['0'])[0])],'total':2})
            if path=='/__knowledge_stream__':return self.respond(b'data: {"line":"synthetic task"}\n\ndata: {"done":true,"ok":true}\n\n',kind='text/event-stream')
            data={'/__knowledge_run__':{'running':False},'/__knowledge_corrections__':{'actions':[]},'/__knowledge_settings__':settings,'/__knowledge_usage__':usage,'/__knowledge_quality__':{'counts':{'cards':1},'categories':{},'stages':{},'examples':[{'stage':'review','category':'projects','reason':'unknown','record_id':'project1','source_ids':[]}],'jobs':[]},'/__staging__':{'files':[]},'/__model_settings__':model,'/__onboarding__':guide,'/__privacy__':privacy}.get(path)
            if path=='/__privacy__' and state.get('hold_privacy'):release.wait(10)
            if data is not None:return self.respond(data)
            self.send_error(404)
        def do_POST(self):
            path=urlsplit(self.path).path;body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or b'{}');counts['POST '+path]+=1;posts.append((path,body))
            if path=='/fixture-control':
                state.update(body)
                if state['hold'] or state.get('hold_privacy'):release.clear()
                else:release.set()
                return self.respond({})
            if path in ['/auth/setup','/auth/login']:return self.respond({'error_code':'auth_error'},422)
            if path=='/chat':return self.respond({'reply':'Literal fixture reply '+str(counts['POST /chat'])})
            if path=='/__knowledge_correct__':return self.respond({})
            if path=='/__privacy__':return self.respond(privacy)
            if path=='/__onboarding__':return self.respond(guide)
            self.send_error(404)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:yield f'http://127.0.0.1:{server.server_port}',counts
    finally:release.set();server.shutdown();server.server_close()


@pytest.mark.parametrize('locale,width,theme',[('en',1280,'light'),('en',390,'dark'),('zh-CN',1280,'dark'),('zh-CN',390,'light')])
def test_refreshed_native_dashboard_every_owner_and_accessible_workflows(tmp_path,interfaces_server,locale,width,theme):
    url,counts=interfaces_server
    checks=r"""(async()=>{
 const get=id=>document.getElementById(id),assert=(value,message)=>{if(!value)throw Error(message);};
 const wait=async predicate=>{const until=Date.now()+7000;while(!predicate()){if(Date.now()>until)throw Error('native state timeout');await new Promise(resolve=>setTimeout(resolve,20));}};
 const stats=async()=>await(await fetch('/fixture-stats')).json(),control=async body=>await fetch('/fixture-control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 const rgba=value=>{const a=value.match(/[0-9.]+/g).map(Number);return [...a.slice(0,3),a[3]??1];},blend=(a,b)=>a.slice(0,3).map((v,i)=>v*a[3]+b[i]*(1-a[3]));
 const lum=rgb=>rgb.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
 function surface(selector){const e=document.querySelector(selector);assert(e,'Missing surface '+selector);e.focus();assert(document.activeElement===e,'Focus failed '+selector);const s=getComputedStyle(e);assert(s.outlineStyle!=='none','Missing outline '+selector);assert(s.transitionDuration.split(',').every(v=>parseFloat(v)<=.001),'Reduced motion failed '+selector);assert(document.documentElement.scrollWidth<=innerWidth,'Viewport overflow '+selector);const bg=blend(rgba(s.backgroundColor),rgba(getComputedStyle(document.body).backgroundColor)),fg=e.tagName==='BUTTON'?blend(rgba(s.color),[...bg,1]):blend(rgba(s.borderTopColor),[...bg,1]);const a=lum(fg),b=lum(bg),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);assert(ratio>=(e.tagName==='BUTTON'?4.5:3),'Contrast failed '+selector+' '+ratio);}
 selfosI18n.setLocale(LOCALE);if(THEME==='dark')selfosUI.module('theme').toggle();
 await wait(()=>get('kb-list').children.length>0&&selfosUI.module('jobs').snapshot().phase==='idle');await new Promise(resolve=>setTimeout(resolve,100));assert(customKept,'Custom script removed');
 const before=await stats(),owners=['auth','account','settings','theme','jobs','import-settings','usage','publication','quality','overview','staging','onboarding','chat','dimensions','privacy','sparklines','knowledge','corrections','timeline'];
 for(const owner of owners){const source=document.querySelector('script[data-selfos-module="'+owner+'"]').textContent,repeat=document.createElement('script');repeat.textContent=source;document.body.append(repeat);}
 selfosUI.init(document);selfosUI.init(document);selfosUI.init(document);get('custom-control').click();await new Promise(resolve=>setTimeout(resolve,50));const repeated=await stats();for(const [path,count]of Object.entries(before.counts))if(path.startsWith('/__'))assert(repeated.counts[path]===count,'Duplicate startup '+path);assert(!repeated.counts['POST /chat']&&!repeated.counts['/__model_test__'],'Initialization sent provider request');surface('#knowledge-btn');
 selfosUI.module('chat').setMode('conversation');selfosUI.module('chat').open();surface('#chat-input');get('chat-input').value='Native typed question';get('chat-input').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));await wait(()=>selfosUI.module('chat').snapshot().history.length===2);assert((await stats()).counts['POST /chat']===1,'Typed event sent twice');get('chat-input').value='Preserved draft';
 document.querySelector('.grid .card').querySelector('.card-header').click();assert(get('dim-modal').classList.contains('open'),'Nested card action failed');document.querySelector('[data-selfos-action="dimensions.discuss"]').click();await wait(()=>selfosUI.module('chat').snapshot().history.length===4);assert((await stats()).counts['POST /chat']===2&&get('chat-input').value==='Preserved draft','Dimension send duplicated or reset draft');selfosUI.module('chat').toggle();
 surface('#kb-search');get('kb-list').querySelector('.kb-card').click();await wait(()=>get('kb-detail-content').querySelector('[data-selfos-action="knowledge.source"]'));surface('#kb-close');
 get('kb-detail-content').querySelector('[data-selfos-action="knowledge.source"]').click();await wait(()=>get('kb-detail-content').querySelector('pre'));get('kb-detail-content').querySelector('[data-selfos-action="knowledge.source"]').click();await wait(()=>get('kb-detail-content').textContent.includes('retained tail'));const sourceBefore=(await stats()).counts['/__knowledge_source__'];selfosI18n.setLocale(selfosI18n.locale==='en'?'zh-CN':'en');assert(get('kb-detail-content').textContent.includes('Literal original <source>'),'Locale altered source');assert((await stats()).counts['/__knowledge_source__']===sourceBefore,'Locale reread source');
 get('kb-detail-content').querySelector('[data-correction-edit]').click();const correction=get('kb-detail-content').querySelector('[data-correction-text]');correction.value='Native corrected context';correction.closest('form').requestSubmit();await wait(()=>!get('kb-detail').open);assert((await stats()).counts['POST /__knowledge_correct__']===1,'Correction submitted twice');
 await selfosUI.module('knowledge').openDetail('project1');get('kb-detail-content').querySelector('[data-selfos-action="knowledge.timeline"]').click();await wait(()=>get('pt-current').textContent.includes('Current fixture goal'));surface('#pt-close');get('pt-filter').value='blockers';get('pt-filter').dispatchEvent(new Event('change',{bubbles:true}));await wait(()=>!get('pt-more').disabled);get('pt-more').click();await wait(()=>get('pt-list').children.length===2);get('pt-list').querySelector('[data-selfos-action="timeline.source"]').click();await wait(()=>get('pt-list').querySelector('pre'));get('pt-list').querySelector('[data-selfos-action="timeline.source"]').click();await wait(()=>get('pt-list').textContent.includes('retained tail'));get('pt-close').click();
 await selfosUI.module('settings').open();surface('#app-settings .settings-close');get('app-settings').close();await selfosUI.module('settings').openModel();surface('#model-settings button[type=submit]');get('model-settings').close();
 await selfosUI.module('import-settings').open();surface('#workload-save');get('knowledge-custom').value='Dirty import draft';get('knowledge-custom').dispatchEvent(new Event('input',{bubbles:true}));selfosUI.module('import-settings').close();await selfosUI.module('privacy').open();surface('#privacy-rules');get('privacy-rules').value='C:/synthetic/private';get('privacy-rules').dispatchEvent(new Event('input',{bubbles:true}));selfosUI.module('privacy').close();
 await selfosUI.module('onboarding').open();surface('#onboarding-skip');get('onboarding-roots').value='C:/dirty-source-draft';get('onboarding-roots').dispatchEvent(new Event('input',{bubbles:true}));const beforeModelReturn=(await stats()).counts['/__onboarding__'];selfosUI.module('onboarding').configureModel();await wait(()=>get('model-settings').open&&!get('onboarding-dialog').open);get('model-settings').close();await wait(()=>get('onboarding-dialog').open);await new Promise(resolve=>setTimeout(resolve,100));assert((await stats()).counts['/__onboarding__']===beforeModelReturn+1,'Model return hook duplicated guide read');selfosUI.module('onboarding').close();
 await selfosUI.module('settings').open();document.querySelector('[data-selfos-action="account.change"]').click();surface('#auth-change button[type=submit]');get('auth-current').value='Synthetic current';get('auth-new').value='Synthetic next';get('auth-new-confirm').value='Mismatch';get('auth-change').querySelector('form').requestSubmit();assert(get('auth-change-status').textContent===selfosI18n.t('auth.mismatch'),'Confirmation validation failed');assert(!(await stats()).counts['POST /auth/change'],'Invalid confirmation sent request');document.querySelector('[data-selfos-action="account.close"]').click();
 await control({hold:true});const pending=selfosUI.module('knowledge').openDetail('project1');await wait(()=>requestRecords.some(record=>record.url.startsWith('/__knowledge_item__')&&record.signal&&!record.signal.aborted));const active=[...requestRecords].reverse().find(record=>record.url.startsWith('/__knowledge_item__'));selfosUI.teardown();assert(active.signal.aborted,'Knowledge body survived teardown');await control({hold:false});await pending;for(const id of ['knowledge-library','kb-detail','project-timeline']){const root=get(id);root.replaceWith(root.cloneNode(true));}selfosUI.init(document);await wait(()=>get('kb-detail-content').textContent.includes('Fixture project'));assert(get('kb-detail').matches(':modal'),'Remount lost native modal');assert(get('chat-input').value==='Preserved draft'&&get('privacy-rules').value==='C:/synthetic/private'&&get('onboarding-roots').value==='C:/dirty-source-draft','Remount reset draft');assert(selfosUI.module('chat').snapshot().history.length===4,'Remount reset chat history');assert(get('pt-list').textContent.includes('retained tail'),'Timeline remount discarded original cache');assert(!pageErrors.length,pageErrors.join(';'));selfosUI.teardown();return 'all native owner workflows passed';
 })()""".replace('LOCALE',json.dumps(locale)).replace('THEME',json.dumps(theme))
    run_chromium(tmp_path,url+'/',checks,width=width)
    assert counts['POST /chat']==2 and counts['POST /__knowledge_correct__']==1
    assert not counts['POST /auth/change'] and not counts['/__model_test__']


def test_native_standalone_login_validation_reinit_locked_state_and_cleanup(tmp_path,interfaces_server):
    url,counts=interfaces_server
    checks=r"""(async()=>{
 const get=id=>document.getElementById(id),assert=(v,m)=>{if(!v)throw Error(m);},wait=async predicate=>{const until=Date.now()+5000;while(!predicate()){if(Date.now()>until)throw Error('login timeout');await new Promise(resolve=>setTimeout(resolve,20));}};
 await wait(()=>!get('auth-form').hidden);const before=requestRecords.length,source=document.querySelector('script[data-selfos-module="login"]').textContent,repeat=document.createElement('script');repeat.textContent=source;document.body.append(repeat);selfosUI.init(document);selfosUI.init(document);selfosUI.init(document);assert(requestRecords.length===before,'Login status repeated');
 get('auth-password').value='Synthetic next password';get('auth-confirm').value='Synthetic mismatch';get('auth-form').requestSubmit();assert(!requestRecords.some(record=>record.url==='/auth/setup'),'Invalid confirmation sent setup');get('auth-confirm').value='Synthetic next password';get('auth-form').requestSubmit();await wait(()=>!get('auth-submit').disabled);assert(requestRecords.filter(record=>record.url==='/auth/setup').length===1,'Login event submitted twice');assert(!get('auth-password').value&&!get('auth-confirm').value,'Failure retained credentials');selfosI18n.setLocale('zh-CN');assert(get('auth-status').textContent===selfosI18n.t('auth.auth_error'),'Login failure lost localized binding');
 await fetch('/fixture-control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({auth:'locked'})});await selfosUI.module('login').refresh();assert(get('auth-form').hidden&&!get('auth-recovery').hidden,'Locked state lost');get('auth-password').value='Teardown secret';selfosUI.teardown();assert(!get('auth-password').value&&!get('auth-confirm').value,'Teardown retained credentials');assert(!pageErrors.length,pageErrors.join(';'));return 'standalone login native passed';
 })()"""
    run_chromium(tmp_path,url+'/login',checks)
    assert counts['POST /auth/setup']==1


@pytest.mark.parametrize('interfaces_server',['pre45'],indirect=True)
def test_native_pre45_cached_page_uses_current_owners_and_actions(tmp_path,interfaces_server):
    test_refreshed_native_dashboard_every_owner_and_accessible_workflows(tmp_path,interfaces_server,'en',390,'dark')


@pytest.mark.parametrize('cloned',[False,True])
def test_native_pending_privacy_and_unsaved_correction_search_remount(tmp_path,interfaces_server,cloned):
    url,counts=interfaces_server
    checks=r"""(async()=>{
 const get=id=>document.getElementById(id),pause=ms=>new Promise(r=>setTimeout(r,ms)),assert=(value,message)=>{if(!value)throw Error(message);},wait=async predicate=>{const end=Date.now()+7000;while(!predicate()){if(Date.now()>end)throw Error('remount wait timeout');await pause(20);}},control=body=>fetch('/fixture-control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 await wait(()=>get('kb-list').textContent.includes('Fixture project'));
 const privacy=selfosUI.module('privacy');await control({hold_privacy:true});const opening=privacy.open();await wait(()=>requestRecords.some(record=>record.url==='/__privacy__'));
 get('privacy-rules').value='Dirty private rules';get('privacy-rules').dispatchEvent(new Event('input',{bubbles:true}));selfosUI.teardown();if(CLONED){const root=get('privacy-settings');root.replaceWith(root.cloneNode(true));}selfosUI.init(document);await pause(100);await control({hold_privacy:false});await opening;await wait(()=>get('privacy-destination').textContent.includes('Fixture model'));assert(get('privacy-rules').value==='Dirty private rules','Privacy dirty rules lost');await privacy.save();assert(requestRecords.filter(record=>record.url==='/__privacy__'&&record.body).length===1,'Privacy save unavailable');privacy.close();await pause(20);
 await selfosUI.module('knowledge').openDetail('project1');get('kb-detail').close();await selfosUI.module('knowledge').openDetail('project1');await pause(50);assert(get('kb-detail-content').querySelector('[data-selfos-action="knowledge.timeline"]'),'Queued old close invalidated reopened detail');
 for(const mode of ['edit','merge']){
  await selfosUI.module('knowledge').openDetail('project1');get('kb-detail-content').querySelector('[data-correction-'+mode+']').click();const text=get('kb-detail-content').querySelector('[data-correction-text]');text.value='Unsaved '+mode;const candidates=get('kb-detail-content').querySelector('[data-correction-candidates]');if(candidates)candidates.options[0].selected=true;
  selfosUI.teardown();if(CLONED)for(const id of ['knowledge-library','kb-detail']){const root=get(id);root.replaceWith(root.cloneNode(true));}selfosUI.init(document);await pause(100);
  assert(get('kb-detail-content').querySelector('[data-correction-text]')?.value==='Unsaved '+mode,'Correction draft lost');if(mode==='merge')assert(get('kb-detail-content').querySelector('[data-correction-candidates]').selectedOptions[0]?.value==='project2','Merge selection lost');assert(!requestRecords.some(record=>record.url==='/__knowledge_correct__'),'Remount sent correction');get('kb-detail').close();await pause(20);
 }
 const before=requestRecords.filter(record=>record.url.startsWith('/__knowledge__?')).length;get('kb-search').value='Pending remount query';get('kb-search').dispatchEvent(new Event('input',{bubbles:true}));selfosUI.teardown();selfosUI.init(document);await wait(()=>requestRecords.filter(record=>record.url.startsWith('/__knowledge__?')).length===before+1);await pause(300);const queries=requestRecords.filter(record=>record.url.startsWith('/__knowledge__?'));assert(queries.length===before+1&&new URL(queries.at(-1).url,location.origin).searchParams.get('query')==='Pending remount query','Pending search lost or duplicated');selfosUI.teardown();return 'pending privacy, correction and search remount passed';
 })()""".replace('CLONED',str(cloned).lower())
    run_chromium(tmp_path,url+'/',checks,width=1280)
    assert counts['POST /__privacy__']==1 and not counts['POST /__knowledge_correct__']
