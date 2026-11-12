"""Explicit real-browser integration; not collected as unit tests."""
import argparse
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path


def worker():
    source=Path(sys.argv[2]).resolve()
    if not (source/'.selfos-integration-source').is_file():
        raise RuntimeError('Worker requires a synthetic source directory')
    import selfos.app.knowledge as knowledge
    import selfos.app.knowledge_cli as cli
    knowledge.local_roots=cli.local_roots=lambda:[source]
    sys.argv=[sys.argv[0],*sys.argv[3:]]
    cli.main()


def run_case(browser,output,locale,width,theme,motion):
    from integration_fixture import create_profile, ModelFixture
    from selfos.security.auth import AuthManager
    from selfos.web.rendering.dashboard import generate_dashboard
    import selfos.web.server as runtime
    import selfos.app.jobs as jobs
    import selfos.app.library as library
    label=f'{locale}-{width}-{theme}-{motion}'
    result={'case':label,'stage':'setup','passed':False}
    with tempfile.TemporaryDirectory(prefix='selfos-integration-') as directory,ModelFixture() as model:
        root=Path(directory); vault=root/'vault'; vault.mkdir()
        password='Synthetic integration password'
        auth=AuthManager(root,vault,directory=root/'auth'); auth.setup(password)
        profile=create_profile(root)
        (root/'.selfos-model.json').write_text(json.dumps({'provider':'openai','model':'fixture-model',
            'base_url':model.base_url,'api_key':'synthetic-fixture-key','proxy_mode':'direct','proxy_url':''}),encoding='utf-8')
        runtime.ROOT=root; runtime.VAULT=vault
        with runtime.KNOWLEDGE_RUN_LOCK:
            runtime.KNOWLEDGE_RUN.clear()
            runtime.KNOWLEDGE_RUN.update(stop_file=None,process=None,job_id=None,phase='idle',
                saved=set(),total=0,last_line='',result=None)
        runtime.DASHBOARD=generate_dashboard(vault,scores={k:6 for k in ['career','work','health','learning','research','life','family']})
        library.local_roots=lambda:[profile['source_root'],profile['ui_sources']]
        original_command=jobs.command
        def fixture_command(name,app_root,*options):
            if name!='knowledge':raise AssertionError('Unexpected background task')
            return [sys.executable,'-u',str(Path(__file__).resolve()),'--worker',str(profile['source_root']),
                    '--root',str(app_root),'--workers','1',*options]
        jobs.command=fixture_command
        class Handler(runtime.Handler):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler); server.auth=auth
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        context=browser.new_context(viewport={'width':width,'height':900},reduced_motion=motion)
        preferred='unsupported-fixture-locale' if locale=='en' and width==1280 else locale
        context.add_init_script('localStorage.setItem("selfos-lang",'+json.dumps(preferred)+');localStorage.setItem("selfos-theme",'+json.dumps(theme)+');')
        errors=[]; external=[]
        def guard(route):
            if route.request.url.startswith(url+'/'):route.continue_()
            else:external.append(route.request.url); route.abort()
        context.route('**/*',guard)
        page=context.new_page(); page.on('pageerror',lambda error:errors.append(str(error)))
        page.set_default_timeout(12000)
        try:
            result['stage']='authentication'
            assert context.request.get(url+'/__knowledge__').status==401
            page.goto(url)
            assert page.evaluate('window.selfosI18n.locale')==locale
            page.locator('#auth-password').fill('Wrong synthetic password')
            with page.expect_response(lambda r:'/auth/' in r.url):page.locator('#auth-submit').click()
            assert page.locator('#auth-form').is_visible()
            page.locator('#auth-password').fill(password); page.locator('#auth-submit').click()
            page.locator('#kb-list .kb-card').first.wait_for()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert page.locator('body').evaluate('(b)=>b.classList.contains("dark")')==(theme=='dark')
            assert page.evaluate('matchMedia("(prefers-reduced-motion: reduce)").matches')==(motion=='reduce')
            result['stage']='overall navigation'
            page.locator('.knowledge-overall').focus(); page.keyboard.press('Enter')
            page.wait_for_function('(()=>{const r=document.getElementById("dimension-cards").getBoundingClientRect();return location.hash==="#dimension-cards"&&r.bottom>0&&r.top<innerHeight;})()')
            result['stage']='model and network settings'
            page.locator('#current-model').filter(has_text='fixture-model').wait_for(state='attached')
            held=[]
            def delayed_config(route):
                if route.request.method=='GET':held.append(route)
                else:route.continue_()
            context.route('**/__model_settings__',delayed_config)
            page.locator('#model-settings-entry button').click()
            page.locator('#app-settings button[onclick*="openModelSettings"]').click()
            page.locator('#model-settings button[data-i18n="ui.model.close"]').click()
            page.locator('#model-settings-entry button').click()
            page.locator('#app-settings button[onclick*="openModelSettings"]').click()
            from selfos.providers.settings import public_config
            assert len(held)==2
            with page.expect_response(lambda r:r.url.endswith('/__model_settings__')):
                held[0].fulfill(json=public_config(root))
            assert page.locator('#model-name').is_disabled()
            held[1].fulfill(json=public_config(root))
            context.unroute('**/__model_settings__',delayed_config)
            page.locator('#model-provider').select_option('openai')
            page.locator('#model-base').fill(model.base_url)
            page.locator('#model-name').fill('fixture-model')
            page.locator('#model-proxy-mode').select_option('manual')
            page.locator('#model-proxy-url').fill('http://127.0.0.1:9')
            page.evaluate('window.fixtureFocus=document.activeElement;window.selfosI18n.setLocale('+json.dumps('zh-CN' if locale=='en' else 'en')+')')
            assert page.locator('#model-name').input_value()=='fixture-model'
            assert page.locator('#model-proxy-url').input_value()=='http://127.0.0.1:9'
            assert page.evaluate('document.activeElement===window.fixtureFocus')
            page.evaluate('window.selfosI18n.setLocale("en")')
            test_button=page.locator('#model-settings button[onclick*="saveModelSettings(true)"]')
            model.fail_test=True; test_button.click()
            page.locator('#model-status').filter(has_text='Could not complete').wait_for()
            model.fail_test=False; page.locator('#model-proxy-mode').select_option('direct'); test_button.click()
            page.locator('#model-status').filter(has_text='passed').wait_for()
            page.locator('#model-settings button[onclick*=".close()"]').click()
            result['stage']='search, pagination and raw sources'
            page.evaluate('window.browseKnowledge("lessons")')
            page.locator('#kb-list .kb-card').first.wait_for()
            first=page.locator('#kb-list .kb-card').count(); page.locator('#kb-more').click()
            page.wait_for_function('(n)=>document.querySelectorAll("#kb-list .kb-card").length>n',arg=first)
            page.locator('#kb-search').fill('Fixture lesson 07'); page.locator('#kb-search').press('Enter')
            page.wait_for_function('document.querySelectorAll("#kb-list .kb-card").length===2')
            page.locator('#kb-source-filter').select_option('codex')
            page.wait_for_function('document.querySelectorAll("#kb-list .kb-card").length===1')
            page.locator('#kb-date-from').fill('2027-01-01')
            page.locator('#kb-date-from').dispatch_event('change')
            page.wait_for_function('document.querySelectorAll("#kb-list .kb-card").length===0')
            page.locator('#kb-date-from').fill('2026-01-01')
            page.locator('#kb-date-from').dispatch_event('change')
            page.wait_for_function('document.querySelectorAll("#kb-list .kb-card").length===1')
            page.locator('#kb-list .kb-card').first.click(); page.locator('#kb-sources button').first.click()
            page.locator('#kb-sources pre').filter(has_text='reliable checkpointed knowledge import').wait_for()
            page.locator('#kb-close').click(); page.locator('#kb-reset').click()
            page.evaluate('window.browseKnowledge("projects")')
            page.locator('#kb-list .kb-card').first.click(); page.locator('[data-project-timeline]').click()
            result['stage']='timeline filters and pagination'
            page.locator('#pt-list .pt-milestone').first.wait_for()
            count=page.locator('#pt-list .pt-milestone').count(); page.locator('#pt-more').click()
            page.wait_for_function('(n)=>document.querySelectorAll("#pt-list .pt-milestone").length>n',arg=count)
            page.locator('#pt-filter').select_option('decisions')
            page.wait_for_function('document.getElementById("pt-more").disabled===false&&document.querySelectorAll("#pt-list .pt-milestone").length>0')
            assert 'Fixture decision' in page.locator('#pt-list').inner_text()
            assert 'Fixture next step' not in page.locator('#pt-list').inner_text()
            page.locator('#pt-close').click()
            if width==1280 and theme=='light':
                result['stage']='real CLI stream, reload, stop and resume'
                model.block_second=True; model.gate.clear(); page.locator('.knowledge-primary').click()
                page.locator('#progress-log').filter(has_text='Saved session 1/2').wait_for(timeout=25000)
                assert model.blocked.wait(5)
                page.evaluate('refreshImportPublication()')
                assert 'Projects: 1' in page.locator('#import-modal-published').text_content()
                assert 'Experience: 61' in page.locator('#import-modal-published').text_content()
                assert 'Saved sessions are not published knowledge' in page.locator('#import-modal-boundary').text_content()
                before=model.extractions; page.evaluate('window.selfosI18n.setLocale("zh-CN")')
                assert model.extractions==before
                page.reload(); page.locator('#knowledge-stop-btn').wait_for()
                page.locator('#knowledge-stop-btn').click(); model.gate.set()
                page.wait_for_function('!document.getElementById("knowledge-stop-btn").offsetParent',timeout=25000)
                status=context.request.get(url+'/__knowledge_run__').json()
                assert status['result']['cancelled']
                page.evaluate('document.getElementById("progress-modal").classList.remove("open");window.selfosI18n.setLocale("en")')
                page.evaluate('refreshImportPublication()')
                page.locator('#import-publication summary').click()
                assert 'provisional' in page.locator('#import-provisional').text_content()
                assert 'Saved extraction checkpoints' in page.locator('#import-checkpoints').text_content()
                assert 'Experience: 61' in page.locator('#import-published').text_content()
                model.block_second=False; page.locator('#import-operations button[data-action="resume"]').first.click()
                page.locator('#progress-title').filter(has_text='Knowledge complete').wait_for(timeout=30000)
                status=context.request.get(url+'/__knowledge_run__').json(); assert status['result']['ok']
                published=json.loads((vault/'.knowledge_pipeline.json').read_text(encoding='utf-8'))
                assert len(published['cards'])==2
                assert all(card['title']=='Fixture imported project' for card in published['cards'].values())
                assert model.extractions<=3,'Resume reprocessed an already saved session'
                assert model.extraction_sessions.count(model.extraction_sessions[0])==1,'First saved session was processed again'
                page.evaluate('document.getElementById("progress-modal").classList.remove("open")')
                page.evaluate('refreshImportPublication()')
                assert 'Projects: 2' in page.locator('#import-published').text_content()
                assert 'Experience: 0' in page.locator('#import-published').text_content()
                assert 'This snapshot is already published' in page.locator('#import-operations').text_content()
            for path,data in profile['original_bytes'].items():assert path.read_bytes()==data
            assert not errors,errors
            assert not external,external
            page.evaluate('window.selfosI18n.setLocale('+json.dumps(locale)+')')
            page.screenshot(path=str(output/(label+'.png')),full_page=False)
            result['stage']='logout'
            page.locator('#model-settings-entry button').click()
            page.locator('#auth-account-buttons button[data-i18n="auth.logout"]').click()
            page.locator('#auth-form').wait_for()
            assert context.request.get(url+'/__knowledge__').status==401
            result.update(passed=True,model_fixture_requests=len(model.requests))
        except Exception as error:
            result['error']=str(error)
            print(result,flush=True)
            try:page.screenshot(path=str(output/(label+'-failure.png')),full_page=False,timeout=3000)
            except Exception:pass
            raise
        finally:
            model.gate.set()
            proc=runtime.KNOWLEDGE_RUN.get('process')
            if proc and proc.poll() is None:
                marker=runtime.KNOWLEDGE_RUN.get('stop_file')
                if marker:marker.touch()
                try:proc.wait(timeout=10)
                except Exception:proc.terminate(); proc.wait(timeout=5)
            context.close(); server.shutdown(); server.server_close(); thread.join(timeout=5)
            jobs.command=original_command
            (output/(label+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    if '--worker' in sys.argv:
        worker(); raise SystemExit
    parser=argparse.ArgumentParser(); parser.add_argument('--browser',required=True)
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--package-path',type=Path)
    args=parser.parse_args()
    package=args.package_path.resolve() if args.package_path else Path(__file__).resolve().parents[2]/'src'
    sys.path.insert(0,str(package))
    import selfos
    assert Path(selfos.__file__).resolve().is_relative_to(package)
    from playwright.sync_api import sync_playwright
    args.output=args.output.resolve(); args.output.mkdir(parents=True,exist_ok=True)
    results=[]
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(executable_path=args.browser,headless=True)
        try:
            for case in [('en',1280,'light','no-preference'),('zh-CN',390,'dark','reduce'),
                         ('zh-CN',1280,'dark','no-preference'),('en',390,'light','reduce')]:
                results.append(run_case(browser,args.output,*case)); print(case,'passed',flush=True)
        finally:browser.close()
    (args.output/'results.json').write_text(json.dumps({'package':str(selfos.__file__),
        'python':sys.version,'results':results},indent=2),encoding='utf-8')
