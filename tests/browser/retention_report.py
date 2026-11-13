"""Synthetic browser verification; no discovery or model requests."""
import json
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))


def main():
    from playwright.sync_api import sync_playwright
    from integration_fixture import create_profile
    from selfos.web.rendering.dashboard import generate_dashboard
    from selfos.web.rendering.resources import frontend_text
    from selfos.web.i18n import runtime as i18n_runtime
    from selfos.security.auth import AuthManager
    import selfos.web.server as runtime
    browser_path=sys.argv[1]
    results=[]
    with tempfile.TemporaryDirectory(prefix='selfos-quality-browser-') as directory:
        root=Path(directory); profile=create_profile(root);vault=profile['vault']
        runtime.ROOT=root;runtime.VAULT=vault
        (vault/'.knowledge_sources.json').write_text(json.dumps({'version':1,
            'roots':[str(profile['source_root']),str(profile['ui_sources'])], 'exclusions':[]}),encoding='utf-8')
        runtime.DASHBOARD=generate_dashboard(vault,scores={k:6 for k in ['career','work','health','learning','research','life','family']})
        auth=AuthManager(root,vault,directory=root/'auth');auth.reset('synthetic quality password')
        panel=('<html><head>'+i18n_runtime()+'</head><body>'+frontend_text('templates/knowledge-quality.html')+'</body></html>').encode('utf-8')
        from selfos.app.quality_report import quality_report
        data=quality_report(vault)
        class Handler(runtime.Handler):
            def log_message(self,*args):pass
            def do_GET(self):
                if self.path=='/':
                    if self._auth_guard():self._send(200,panel,'text/html; charset=utf-8')
                else:super().do_GET()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.auth=auth
        threading.Thread(target=server.serve_forever,daemon=True).start()
        url=f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=browser_path,headless=True)
                context=browser.new_context(viewport={'width':1280,'height':900})
                context.add_cookies([{'name':'selfos_session','value':auth.login('synthetic quality password'),'url':url}])
                context.add_init_script('localStorage.setItem("selfos-lang","en");')
                page=context.new_page();errors=[]
                def render_route(route):
                    if route.request.url==url+'/':route.fulfill(status=200,body=panel,content_type='text/html; charset=utf-8')
                    elif route.request.url==url+'/__knowledge_quality__':route.fulfill(status=200,body=json.dumps(data),content_type='application/json')
                    else:route.abort()
                page.route('**/*',render_route)
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(url,wait_until='domcontentloaded')
                page.locator('#knowledge-quality summary').click()
                try:page.wait_for_function('document.querySelectorAll("#quality-content article").length >= 4',timeout=10000)
                except Exception:
                    print('Panel status',page.locator('#quality-status').inner_text(),'Errors',errors,flush=True)
                    response=context.request.get(url+'/__knowledge_quality__');print('API',response.status,response.text()[:1000],flush=True)
                    raise
                for locale,width in [('en',1280),('zh-CN',390)]:
                    print('Checking',locale,width,flush=True)
                    page.set_viewport_size({'width':width,'height':900})
                    page.evaluate('(locale)=>window.selfosI18n.setLocale(locale)',locale)
                    report=page.locator('#knowledge-quality')
                    text=report.inner_text()
                    assert ('No sufficient eligibility evidence' if locale=='en' else '缺少足够资格证据') in text
                    assert 'quality.' not in text and 'search.' not in text
                    assert report.evaluate('(e)=>e.scrollWidth <= e.clientWidth+1')
                    assert not errors,errors
                    links=report.locator('a[href^="/__knowledge_source__"]')
                    assert links.count()>0
                    response=context.request.get(url+links.first.get_attribute('href'))
                    print('Checked source',response.status,flush=True)
                    assert response.status==200
                    results.append({'locale':locale,'width':width,'passed':True,'source_status':response.status})
                context.close()
                browser.close()
        finally:server.shutdown();server.server_close()
    print(json.dumps(results))


if __name__=='__main__':main()
