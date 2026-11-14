"""Synthetic Chromium check using native CDP (no browser package required)."""
import os
import shutil
import socket
import subprocess
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen
import pytest
from selfos.web.i18n import runtime
from selfos.web.rendering.resources import frontend_text


def test_model_discovery_browser_preserves_draft_and_ignores_stale_results(tmp_path):
    node=shutil.which('node')
    chrome=Path(os.environ.get('SELFOS_CHROME','C:/Users/I748319/.cache/puppeteer/chrome/win64-135.0.7049.95/chrome-win64/chrome.exe'))
    if not node or not chrome.exists():pytest.skip('Node 22+ and SELFOS_CHROME are needed')
    template=frontend_text('templates/settings-model.html')
    for resource in ['styles/settings-model.css','scripts/settings-model.js']:
        template=template.replace('@@SELFOS_RESOURCE:'+resource+'@@',frontend_text(resource))
    fixture=r"""<script>
    window.requests=[];window.releases=[];window.saves=[];window.auths=[];window.pageErrors=[];window.addEventListener('error',event=>pageErrors.push(event.message));
    window.fetch=async(url,options)=>{
      requests.push({url,body:options?.body?JSON.parse(options.body):null,signal:options?.signal});
      if(url==='/__knowledge_run__')return {ok:true,status:200,json:async()=>({running:false})};
      if(url==='/__knowledge_settings__')return {ok:true,status:200,json:async()=>({settings:{domains:['work'],detail:'balanced'},counts:{},saved_checkpoints:0,publication:{operations:[]},usage:{budget:{max_requests:100},runs:[]}})};
      if(url==='/__knowledge_usage__')return {ok:true,status:200,json:async()=>({budget:{max_requests:100},runs:[]})};
      if(url==='/__model_list__')return await new Promise(resolve=>releases.push((status,data)=>resolve({ok:status===200,json:async()=>data})));
      if(url==='/__model_settings__'&&options?.method==='POST')return await new Promise(resolve=>saves.push(()=>resolve({ok:true,json:async()=>({provider:'anthropic',model:'saved',has_api_key:true,proxy_source:'direct',effective_proxy:{}})})));
      if(url==='/auth/change')return await new Promise(resolve=>auths.push(()=>resolve({ok:true,json:async()=>({})})));
      return {ok:true,json:async()=>({provider:'anthropic',model:'saved-model',base_url:'http://fixture',proxy_mode:'direct',proxy_url:'',has_api_key:true,proxy_source:'direct',effective_proxy:{}})};
    };
    </script>"""
    lifecycle='<script>'+frontend_text('scripts/ui-runtime.js')+frontend_text('scripts/ui-request.js')+'</script>'
    bootstrap='<script>'+frontend_text('scripts/ui-bootstrap.js')+'</script>'
    from selfos.web.rendering.auth import account_controls
    account=account_controls(include_runtime=False,include_lifecycle=False)
    from selfos.web.rendering.knowledge import CONTROLS as imports
    jobs='<div id="harvest-modal"></div><div id="progress-modal"><div id="progress-bar"></div><pre id="progress-log"></pre><span id="progress-icon"></span><span id="progress-title"></span><button id="progress-done-btn"></button><button id="knowledge-stop-btn"></button></div><script data-selfos-module="jobs" data-selfos-generation="1">'+frontend_text('scripts/dashboard-imports.js')+'</script>'
    theme='<button id="theme-toggle" data-selfos-action="theme.toggle"></button><button id="lang-toggle" data-selfos-action="theme.language"></button><script>'+frontend_text('scripts/dashboard-theme-language.js')+'</script>'
    html=tmp_path/'fixture.html';html.write_text('<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">'+runtime()+lifecycle+'</head><body>'+fixture+account+template+imports+jobs+theme+bootstrap+'</body></html>',encoding='utf-8')
    checks=r"""(async()=>{
     const get=id=>document.getElementById(id),assert=(v,m)=>{if(!v)throw Error(m);};
     await selfosUI.module('import-settings').open();get('knowledge-custom').value='dirty-fixture-domain';get('knowledge-detail').value='detailed';get('workload-limit').value='777';
     const beforeImport=requests.length,importSource=document.querySelector('script[data-selfos-module="import-settings"]').textContent;
     const importRepeated=document.createElement('script');importRepeated.textContent=importSource;document.body.append(importRepeated);selfosUI.init(document);selfosUI.init(document);selfosUI.init(document);
     assert(requests.length===beforeImport&&get('knowledge-custom').value==='dirty-fixture-domain'&&get('knowledge-detail').value==='detailed'&&get('workload-limit').value==='777','Import settings draft reset or startup reads repeated');
     const unknownAction=document.createElement('button');unknownAction.type='button';unknownAction.dataset.selfosAction='__proto__';get('knowledge-settings').append(unknownAction);unknownAction.click();unknownAction.remove();
     assert(!pageErrors.length&&requests.length===beforeImport,'Unknown action was executed');
     get('workload-save').click();for(let n=0;n<15;n++)await Promise.resolve();
     assert(requests.filter(r=>r.url==='/__knowledge_budget__').length===1,'Budget save invoked more than once');
     selfosUI.module('import-settings').close();
     const settingsButton=get('model-settings-entry').querySelector('button'),nested=document.createElement('span');settingsButton.append(nested);nested.click();
     assert(get('app-settings').open,'Nested settings action did not open dialog');get('app-settings').close();
     get('theme-toggle').click();assert(document.body.classList.contains('dark'),'Theme action failed');
     for(const needle of ['function updateThemeBtn','function openChange']){const source=[...document.scripts].find(s=>s.textContent.includes(needle)).textContent,script=document.createElement('script');script.textContent=source;document.body.append(script);}
     selfosUI.init(document);selfosUI.init(document);assert(document.body.classList.contains('dark'),'Theme reset after reinitialization');
     get('theme-toggle').click();assert(!document.body.classList.contains('dark'),'Duplicate theme listener');
     get('lang-toggle').click();assert(selfosI18n.locale==='zh-CN','Language action failed');selfosI18n.setLocale('en');
     get('app-settings').showModal();document.querySelector('[data-selfos-action="account.change"]').click();
     assert(get('auth-change').open&&!get('app-settings').open,'Account change action failed');
     get('auth-current').value='synthetic current password';get('auth-new').value='synthetic next password';get('auth-new-confirm').value='synthetic mismatch password';
     const beforeAccount=requests.length;get('auth-change').querySelector('form').requestSubmit();
     assert(requests.length===beforeAccount&&get('auth-change-status').textContent,'Invalid confirmation sent auth request');
     document.querySelector('[data-selfos-action="account.close"]').click();assert([...document.querySelectorAll('#auth-change input')].every(e=>e.value===''),'Account close retained credentials');
     await openModelSettings();assert(get('model-load-models'),'Missing discovery button');
     get('model-base').value='http://draft/v1';get('model-key').value='draft-key';get('model-name').value='manual-model';
     get('model-proxy-mode').value='manual';get('model-proxy-url').value='http://draft-proxy:7890';updateModelProxy();
     const count=requests.length,source=[...document.scripts].find(s=>s.textContent.includes('function openAppSettings')).textContent;
     const repeated=document.createElement('script');repeated.textContent=source;document.body.append(repeated);
     selfosUI.init(document);selfosUI.init(document);selfosUI.init(document);
     assert(requests.length===count&&get('model-key').value==='draft-key'&&get('model-base').value==='http://draft/v1','Reinitialization reset draft or requested settings');
     assert(selfosUI.module('settings').openModel===selfosUI.module('settings').openModel,'Missing stable settings API');
     let pending=loadAvailableModels();
     const mountedDialog=get('model-settings'),replacement=mountedDialog.cloneNode(true);mountedDialog.replaceWith(replacement);
     let remountError='';try{selfosUI.init(document);}catch(error){remountError=error.message;}
     assert(remountError.includes('remount-required')&&remountError.includes('busy'),'Busy root replacement was silently accepted');replacement.replaceWith(mountedDialog);selfosUI.init(document);
     assert(requests.at(-1).body.api_key==='draft-key'&&requests.at(-1).body.base_url==='http://draft/v1'&&requests.at(-1).body.proxy_url==='http://draft-proxy:7890','Draft not used');
     assert(get('model-load-models').disabled&&!get('model-name').disabled,'Loading controls wrong');
     selfosI18n.setLocale('zh');assert(get('model-list-status').textContent.includes('正在'),'Chinese loading status missing');releases.at(-1)(200,{models:['a-model','<literal-model>']});await pending;
     assert(get('model-name').value==='manual-model'&&get('model-key').value==='draft-key','Draft overwritten');
     assert(!get('model-available').hidden&&get('model-available').options.length===3,'Missing selection');
     get('model-available').value='<literal-model>';get('model-available').dispatchEvent(new Event('change',{bubbles:true}));
     assert(get('model-name').value==='<literal-model>'&&!get('model-available').querySelector('literal-model'),'Selection unsafe or broken');
     selfosI18n.setLocale('en');assert(get('model-list-status').textContent.includes('models available'),'English loaded status missing');pending=loadAvailableModels();get('model-base').value='http://changed';get('model-base').dispatchEvent(new Event('input',{bubbles:true}));
     releases.at(-1)(200,{models:['stale-model']});await pending;assert(get('model-available').hidden&&get('model-name').value!=='stale-model','Stale accepted');
     for(const [status,data] of [[200,{models:[]}],[422,{code:'model_list_unsupported'}],[502,{code:'model_list_failed'}]]){
       pending=loadAvailableModels();releases.at(-1)(status,data);await pending;
       assert(get('model-available').hidden&&!get('model-load-models').disabled&&get('model-list-status').textContent,'Missing empty/error feedback');
     }
     pending=loadAvailableModels();get('model-settings').close();releases.at(-1)(200,{models:['closed-stale']});await pending;
     await openModelSettings();assert(get('model-available').hidden,'Closed request leaked');
     assert(document.documentElement.scrollWidth<=innerWidth,'Mobile overflow');
     get('auth-current').value='synthetic current password';get('auth-new').value='synthetic next password';get('auth-new-confirm').value='synthetic next password';
     const changing=selfosUI.module('account').changePassword({preventDefault(){},target:get('auth-change').querySelector('form')}),authRequest=requests.at(-1);
     await selfosUI.module('import-settings').open();get('knowledge-custom').value='remount-domain';get('knowledge-custom').dispatchEvent(new Event('input',{bubbles:true}));get('knowledge-detail').value='detailed';get('workload-limit').value='777';
     get('model-name').value='preserved-remount-draft';
     pending=loadAvailableModels();const active=requests.at(-1),saving=selfosUI.module('settings').saveModel(false);selfosUI.teardown();assert(active.signal?.aborted,'Teardown did not cancel active model request');
     assert(authRequest.signal?.aborted,'Teardown did not cancel account request');auths.at(-1)();await changing;
     get('model-key').value='after-teardown-fixture-key';saves.at(-1)();await saving;assert(get('model-key').value==='after-teardown-fixture-key','Stale save modified credentials after teardown');
     releases.at(-1)(200,{models:['after-teardown']});await pending;assert(get('model-available').hidden,'Stale teardown response mounted');
     assert(!requests.some(r=>r.url==='/chat'||r.url==='/__model_test__'),'Lifecycle made model calls');assert(!pageErrors.length,pageErrors.join(';'));
     const importRemounted=get('knowledge-settings').cloneNode(true);get('knowledge-settings').replaceWith(importRemounted);selfosI18n.setLocale('zh');
     get('model-name').value='replacement-default';const remounted=get('model-settings').cloneNode(true);get('model-settings').replaceWith(remounted);selfosUI.init(document);
     assert(get('model-name').value==='preserved-remount-draft'&&get('model-key').value===''&&!get('model-name').disabled,'Explicit remount did not restore safe draft');
     assert(get('model-settings').matches(':modal'),'Explicit remount lost native modal focus behavior');
     assert(get('knowledge-custom').value==='remount-domain'&&get('knowledge-detail').value==='detailed'&&get('workload-limit').value==='777','Import remount lost draft');selfosI18n.setLocale('en');assert(get('knowledge-domains').textContent.includes('Work'),'Import remount lost locale bindings');
     return 'model discovery browser passed';
    })()"""
    harness=r"""
const fs=require('fs');
(async()=>{
 const info=await(await fetch(process.argv[2]+'/json/version')).json(),ws=new WebSocket(info.webSocketDebuggerUrl);
 await new Promise(r=>ws.onopen=r);let seq=0,loadResolve;const pending=new Map();
 ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.method==='Page.loadEventFired'&&loadResolve)loadResolve();if(m.id){const [r,j]=pending.get(m.id);pending.delete(m.id);m.error?j(Error(JSON.stringify(m.error))):r(m.result);}};
 const call=(method,params={},sessionId)=>new Promise((r,j)=>{const id=++seq;pending.set(id,[r,j]);ws.send(JSON.stringify({id,method,params,sessionId}));});
 const {targetId}=await call('Target.createTarget',{url:'about:blank'});
 const {sessionId}=await call('Target.attachToTarget',{targetId,flatten:true});
 await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true},sessionId);
 await call('Page.enable',{},sessionId);const loaded=new Promise(resolve=>loadResolve=resolve);
 await call('Page.navigate',{url:process.argv[3]},sessionId);
 await loaded;await call('Runtime.enable',{},sessionId);
 const out=await call('Runtime.evaluate',{expression:fs.readFileSync(process.argv[4],'utf8'),awaitPromise:true,returnByValue:true},sessionId);
 if(out.exceptionDetails)throw Error(JSON.stringify(out.exceptionDetails));console.log(out.result.value);
 const screenshot=await call('Page.captureScreenshot',{format:'png'},sessionId);fs.writeFileSync(process.argv[4]+'.png',Buffer.from(screenshot.data,'base64'));
 await call('Browser.close');ws.close();process.exit(0);
})().catch(e=>{console.error(e);process.exit(1);});
setTimeout(()=>{console.error('CDP timeout');process.exit(2)},30000);
"""
    script=tmp_path/'browser.cjs';script.write_text(harness,encoding='utf-8')
    check=tmp_path/'checks.js';check.write_text(checks,encoding='utf-8')
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    endpoint=f'http://127.0.0.1:{port}'
    server_requests=[]
    payload=html.read_bytes()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            server_requests.append(self.path)
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
            server_requests.append('sent')
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    process=subprocess.Popen([str(chrome),'--headless=new','--no-sandbox','--disable-gpu','--no-proxy-server',f'--remote-debugging-port={port}',f'--user-data-dir={tmp_path / "chrome"}'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    try:
        for attempt in range(100):
            try:
                with urlopen(endpoint+'/json/version',timeout=1):break
            except OSError:time.sleep(.1)
        else:raise AssertionError('Synthetic browser failed to start')
        result=subprocess.run([node,str(script),endpoint,f'http://127.0.0.1:{server.server_port}',str(check)],capture_output=True,text=True,timeout=40)
        assert result.returncode==0,result.stdout+result.stderr+repr(server_requests)
    finally:
        if process.poll() is None:process.kill()
        server.shutdown();server.server_close()
