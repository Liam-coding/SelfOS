"""Real local authenticated correction UI, synthetic vault and immutable upload."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import uuid
from http.server import ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))


def run(output,browser_path):
    from playwright.sync_api import sync_playwright
    import selfos.web.server as runtime
    from selfos.web.rendering.dashboard import generate_dashboard
    from selfos.security.auth import AuthManager
    from selfos.knowledge.corrections import apply_corrections
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=browser_path,headless=True)
        for locale in ('en','zh-CN'):
            app=output/(locale+'-'+uuid.uuid4().hex[:8]);vault=app/'vault';vault.mkdir(parents=True,exist_ok=True)
            auth=AuthManager(app,vault,directory=app/'auth')
            auth.setup('synthetic browser correction password')
            path=vault/'.knowledge_uploads/originals/synthetic.txt';path.parent.mkdir(parents=True)
            path.write_text('I prefer concise explanations.\nI prefer brief explanations.',encoding='utf-8')
            source={'source':'uploaded_file','path':str(path.relative_to(vault)),
                    'original_filename':'Synthetic conversation.txt','role':'user',
                    'timestamp':'2026-01-01T10:00:00Z','content_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            records=[]
            for value in ('concise','brief'):
                quote=f'I prefer {value} explanations.'
                records.append(dict(key='communication.detail',value=value,text=quote,domain='personal',
                    kind='user_fact',scope_type='global',scope='global',source_ids=['upload1'],
                    supporting_source_ids=['upload1'],supporting_observations=[dict(source_id='upload1',evidence=quote,observed_at=source['timestamp'])],
                    observed_at=source['timestamp'],evidence=quote))
            generated={'cards':{},'lessons':[],'preferences':records,'sources':{'upload1':source}}
            state_path=vault/'.knowledge_pipeline.json';state_path.write_text(json.dumps(generated),encoding='utf-8')
            original_state=state_path.read_bytes();original_source=path.read_bytes()
            runtime.ROOT=app;runtime.VAULT=vault;runtime.DASHBOARD=generate_dashboard(vault)
            class Handler(runtime.Handler):
                def log_message(self,*args):pass
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            server.auth=auth
            token=server.auth.login('synthetic browser correction password')
            threading.Thread(target=server.serve_forever,daemon=True).start()
            url=f'http://127.0.0.1:{server.server_port}'
            context=browser.new_context(viewport={'width':1280,'height':900})
            context.add_cookies([{'name':'selfos_session','value':token,'url':url,'sameSite':'Strict'}])
            context.add_init_script(f"localStorage.setItem('selfos-lang',{json.dumps(locale)})")
            page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            try:
                page.goto(url);page.evaluate("window.browseKnowledge('preferences')")
                page.locator('#kb-list .kb-card').filter(has_text='I prefer concise').first.click()
                page.locator('[data-correction-edit]').wait_for(timeout=3000)
                page.locator('[data-correction-edit]').focus();page.keyboard.press('Enter')
                page.locator('[data-correction-value]').fill('balanced')
                page.locator('[data-correction-text]').fill('Balanced explanations')
                page.evaluate("window.selfosI18n.setLocale('zh-CN')" if locale=='en' else "window.selfosI18n.setLocale('en')")
                assert page.locator('[data-correction-value]').input_value()=='balanced'
                assert page.locator('[data-correction-text]').input_value()=='Balanced explanations'
                page.evaluate('window.selfosI18n.setLocale('+json.dumps(locale)+')')
                page.locator('[data-correction-save]').click()
                page.locator('#kb-list .kb-card').filter(has_text='Balanced explanations').first.wait_for()
                assert state_path.read_bytes()==original_state
                page.reload();page.evaluate("window.browseKnowledge('preferences')")
                page.locator('#kb-list .kb-card').filter(has_text='Balanced explanations').first.click()
                page.locator('[data-correction-delete]').click()
                page.locator('[data-correction-confirm-delete]').click()
                page.locator('[data-correction-undo]').first.wait_for()
                deleted_history=page.locator('#kb-correction-history .kc-history-row').first
                deleted_history.locator('summary').click()
                deleted_history.locator('[data-correction-source]').first.click()
                deleted_history.locator('pre').filter(has_text='I prefer concise explanations.').last.wait_for()
                page.locator('[data-correction-undo]').first.click()
                page.locator('#kb-list .kb-card').filter(has_text='Balanced explanations').first.wait_for()
                page.locator('#kb-list .kb-card').filter(has_text='Balanced explanations').first.click()
                page.locator('[data-correction-merge]').click()
                page.locator('[data-correction-candidates]').select_option(index=0)
                page.locator('[data-correction-text]').fill('Merged explanation preference')
                page.locator('[data-correction-save]').click()
                page.locator('#kb-list .kb-card').filter(has_text='Merged explanation preference').first.wait_for()
                assert page.locator('#kb-list .kb-card').count()==1
                page.locator('#kb-list .kb-card').first.click()
                page.locator('#kb-sources button').first.click()
                page.locator('#kb-sources pre').get_by_text('I prefer concise explanations.',exact=False).wait_for()
                assert path.read_bytes()==original_source and state_path.read_bytes()==original_state
                assert not errors,errors
                page.screenshot(path=str(output/('corrections-'+locale+'.png')),full_page=False)
                print(locale,'keyboard edit, unsaved-language switch, reload, delete, undo, merge and original source passed')
            finally:
                context.close();server.shutdown();server.server_close()
        browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--browser');parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.output:
        args.output.resolve().mkdir(parents=True,exist_ok=True);run(args.output.resolve(),args.browser)
    else:
        with tempfile.TemporaryDirectory(prefix='selfos-corrections-') as temporary:run(Path(temporary),args.browser)
