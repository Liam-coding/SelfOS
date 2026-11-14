"""Authenticated OpenCode acceptance using synthetic SQLite and loopback model only."""
import argparse
import json
import os
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer


def run_case(browser, output, locale):
    from integration_fixture import ModelFixture
    from selfos.security.auth import AuthManager
    from selfos.web.rendering.dashboard import generate_dashboard, _I18N
    from tests.test_opencode_database import create_database
    from tests.test_opencode_export import export_wire
    import selfos.web.server as runtime
    with tempfile.TemporaryDirectory(prefix='selfos-native-ui-') as directory, ModelFixture() as model:
        root = Path(directory)
        vault = root/'vault'
        vault.mkdir()
        auth = AuthManager(root,vault,directory=root/'auth')
        auth.setup('Synthetic native password')
        path, _, _ = create_database(root, count=80)
        with sqlite3.connect(path) as db:
            for index in range(80):
                db.execute('UPDATE part SET data=? WHERE id=?', (json.dumps({'type':'text', 'text':
                    'We are developing a synthetic recoverable knowledge system. Keep immutable originals, exact source permissions and verified backups. ' * 8}), f'prt_{index:04d}_a'))
        db.close()
        (vault/'PROFILE.md').write_text('- Preferred name: Example User', encoding='utf-8')
        (vault/'.knowledge_sources.json').write_text(json.dumps({'version':1,'roots':[],'exclusions':[]}), encoding='utf-8')
        (root/'.selfos-model.json').write_text(json.dumps(dict(provider='openai',model='fixture-model',
            base_url=model.base_url,api_key='synthetic-fixture-key',proxy_mode='direct',proxy_url='')), encoding='utf-8')
        runtime.ROOT, runtime.VAULT = root,vault
        runtime.DASHBOARD = generate_dashboard(vault,scores={key:6 for key in _I18N})
        runtime.KNOWLEDGE_RUN.clear()
        runtime.KNOWLEDGE_RUN.update(stop_file=None,process=None,job_id=None,phase='idle',saved=set(),total=0,last_line='',result=None)
        class Handler(runtime.Handler):
            def log_message(self,*args): pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        server.auth=auth
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        context=browser.new_context(viewport=dict(width=1280 if locale=='en' else 390,height=900))
        context.add_init_script('localStorage.setItem("selfos-lang",'+json.dumps(locale)+');localStorage.setItem("selfos-theme",'+json.dumps('light' if locale=='en' else 'dark')+');')
        context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(url+'/') else route.abort())
        page=context.new_page()
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.set_default_timeout(15000)
        try:
            page.goto(url)
            page.locator('#auth-password').fill('Synthetic native password')
            page.locator('#auth-submit').click()
            page.locator('#uploads-open').wait_for(state='visible')
            page.evaluate('window.openOnboarding()')
            page.locator('#onboarding-next:not([disabled])').click()
            page.locator('#native-path').fill(str(path))
            page.locator('#native-add').click()
            assert page.locator('#native-entries input:checked').count()==1
            assert model.requests==[]
            page.locator('#onboarding-save-sources').click()
            page.locator('#native-entries [data-native-preview]:not([disabled])').click()
            page.locator('#native-start:not([disabled])').wait_for()
            assert model.requests==[]
            assert page.locator('#native-excerpts article').count()==2
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert page.locator('#native-dialog').evaluate('node=>node.scrollWidth<=node.clientWidth'), 'Native dialog clips project path'
            page.locator('#native-dialog').screenshot(path=str(output/(locale+'-native.png')))
            model.block_second=True
            model.gate.clear()
            page.locator('#native-start').click()
            for _ in range(30):
                if model.blocked.is_set(): break
                page.wait_for_timeout(1000)  # Pump routed browser requests while fixture waits.
            assert model.blocked.is_set(), 'Second extraction never reached fixture gate'
            page.locator('#knowledge-stop-btn').click()
            model.gate.set()
            page.wait_for_function("document.getElementById('progress-done-btn').style.display!=='none'",timeout=60000)
            assert not (vault/'.knowledge_pipeline.json').exists(), 'Stopped preview must not publish'
            page.locator('#progress-modal').evaluate("node=>node.classList.remove('open')")
            page.evaluate('window.openOnboarding()')
            page.locator('#native-entries [data-native-preview]:not([disabled])').click()
            page.locator('#native-start:not([disabled])').click()
            page.wait_for_function("document.getElementById('progress-done-btn').style.display!=='none'",timeout=60000)
            state=json.loads((vault/'.knowledge_pipeline.json').read_text(encoding='utf-8'))
            assert state['sources'] and all(source['source']=='opencode' for source in state['sources'].values())
            calls=len(model.requests)
            assert 0<calls<=12
            source_id=next(iter(state['sources']))
            source=page.evaluate('async id=>{const r=await fetch("/__knowledge_source__?id="+id);return {status:r.status,body:await r.json()};}',source_id)
            assert source['status']==200,source
            assert 'synthetic' in source['body']['text'].lower()
            page.locator('#progress-modal').evaluate("node=>node.classList.remove('open')")
            page.locator('#uploads-open').click()
            raw=json.dumps(export_wire(root)).encode()
            page.locator('#uploads-files').set_input_files(dict(name='session.json',mimeType='application/json',buffer=raw))
            page.wait_for_function("document.querySelector('#uploads-queue [data-upload-status=uploaded]')!==null")
            page.locator('#uploads-preview').click()
            page.locator('#uploads-organize:not([disabled])').wait_for()
            assert len(model.requests)==calls
            page.locator('#uploads-dialog').screenshot(path=str(output/(locale+'-export.png')))
            page.locator('#uploads-organize').click()
            page.wait_for_function("document.getElementById('progress-done-btn').style.display!=='none'",timeout=60000)
            state=json.loads((vault/'.knowledge_pipeline.json').read_text(encoding='utf-8'))
            assert any(source.get('provenance')=='quoted_dialogue' for source in state['sources'].values())
            assert errors==[],errors
            return dict(locale=locale,native_parts=2,model_calls=len(model.requests),source_navigation=True,export=True,stop_resume=True)
        finally:
            context.close()
            marker=runtime.KNOWLEDGE_RUN.get('stop_file')
            if marker: marker.touch()
            server.shutdown();server.server_close();thread.join(timeout=5)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--chromium',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if os.environ.get('SELFOS_PLAYWRIGHT_PATH'):sys.path.insert(0,os.environ['SELFOS_PLAYWRIGHT_PATH'])
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from playwright.sync_api import sync_playwright
    args.output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(executable_path=args.chromium,headless=True)
        try: result=[run_case(browser,args.output,locale) for locale in ('en','zh-CN')]
        finally:browser.close()
    print(json.dumps(result))


if __name__=='__main__':main()
