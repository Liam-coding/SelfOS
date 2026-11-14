"""Real source display lifecycle; synthetic originals and authenticated loopback only."""
import argparse
import io
import json
import os
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path


def run_case(browser, locale):
    from selfos.security.auth import AuthManager
    from selfos.sources.upload_admission import admit_document
    from selfos.web.rendering.dashboard import generate_dashboard
    import selfos.web.server as runtime
    with tempfile.TemporaryDirectory(prefix='selfos-source-display-') as directory:
        root = Path(directory)
        vault = root / 'vault'
        vault.mkdir()
        auth = AuthManager(root, vault, directory=root / 'auth')
        auth.setup('Synthetic source password')
        originals = {'alpha.txt': b'Alpha synthetic original.', 'beta.md': b'Beta synthetic original.'}
        docs = {name: admit_document(vault, name, io.BytesIO(raw), len(raw))['document']
                for name, raw in originals.items()}
        runtime.ROOT, runtime.VAULT = root, vault
        runtime.DASHBOARD = generate_dashboard(vault)
        class Handler(runtime.Handler):
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.auth = auth
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{server.server_port}'
        context = browser.new_context(viewport=dict(width=1280 if locale == 'en' else 390, height=900))
        context.add_init_script('localStorage.setItem("selfos-lang",' + json.dumps(locale) + ');')
        context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url + '/') else route.abort())
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.set_default_timeout(10000)
        held = []
        def hold(route):
            # The real authenticated API validates originals; only delivery is delayed.
            response = route.fetch()
            held.append((route, response))
            page.evaluate('window.sourceDeliveries=(window.sourceDeliveries||0)+1')
        def delivery(number):
            page.wait_for_function('window.sourceDeliveries===' + str(number))
            return held.pop(0)
        def view(name):
            page.locator(f'[data-upload-view="{docs[name]["id"]}"]').click()
        try:
            page.goto(url, wait_until='domcontentloaded')
            page.locator('#auth-password').fill('Synthetic source password')
            page.locator('#auth-submit').click()
            page.locator('#uploads-open').click()
            page.locator('[data-upload-view]').first.wait_for()
            view('alpha.txt')
            page.wait_for_function("document.getElementById('uploads-source-text').textContent==='Alpha synthetic original.'")
            page.evaluate("""() => {const native=fetch;window.sourceReplies=0;window.fetch=async(...args)=>{const response=await native(...args);if(String(args[0]).includes('/__knowledge_upload_source__')){const json=response.json.bind(response);response.json=async()=>{try{return await json();}finally{++window.sourceReplies;}};}return response;};}""")
            context.route('**/__knowledge_upload_source__?*', hold)
            view('beta.md')
            page.wait_for_function("document.getElementById('uploads-source-text').textContent===''")
            assert page.locator('#uploads-source-name').inner_text() == 'beta.md'
            assert page.locator('#uploads-source-status').inner_text() == ('Loading original…' if locale == 'en' else '正在加载原文…')
            assert page.locator('#uploads-source-text').get_attribute('aria-busy') == 'true'
            assert page.locator('#uploads-source-status').evaluate("node=>node.closest('[aria-busy=true]')===null")
            assert page.locator('#uploads-source-more').is_hidden()
            opposite = 'zh-CN' if locale == 'en' else 'en'
            page.evaluate('window.selfosI18n.setLocale(' + json.dumps(opposite) + ')')
            assert page.locator('#uploads-source-status').inner_text() == ('正在加载原文…' if opposite == 'zh-CN' else 'Loading original…')
            assert page.locator('#uploads-source-name').inner_text() == 'beta.md'
            assert page.locator('#uploads-source-text').inner_text() == ''
            route, response = delivery(1)
            route.fulfill(response=response)
            page.wait_for_function("document.getElementById('uploads-source-text').textContent==='Beta synthetic original.'")
            assert page.locator('#uploads-source-text').get_attribute('aria-busy') == 'false'
            view('alpha.txt')
            route, _ = delivery(2)
            route.fulfill(status=503, content_type='application/json', body='{"code":"unavailable"}')
            page.locator('#uploads-source-retry').wait_for(state='visible')
            assert page.locator('#uploads-source-text').inner_text() == ''
            assert page.locator('#uploads-source-name').inner_text() == 'alpha.txt'
            assert page.locator('#uploads-source-status').inner_text() == ('Could not load this original. Retry to continue.' if opposite == 'en' else '无法加载这份原文，请重试。')
            page.locator('#uploads-source-retry').click()
            delayed = delivery(3)
            view('beta.md')
            route, response = delivery(4)
            route.fulfill(response=response)
            page.wait_for_function("document.getElementById('uploads-source-text').textContent==='Beta synthetic original.'")
            delayed[0].fulfill(response=delayed[1])
            page.wait_for_function('window.sourceReplies===4')
            page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
            assert page.locator('#uploads-source-name').inner_text() == 'beta.md'
            assert page.locator('#uploads-source-text').inner_text() == 'Beta synthetic original.'
            assert page.locator('#uploads-source-retry').is_hidden()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert errors == [], errors
            assert all((vault / docs[name]['path']).read_bytes() == raw for name, raw in originals.items())
            return dict(locale=locale, delayed=True, failed=True, retried=True, late_response_ignored=True)
        finally:
            for route, _ in held:
                route.abort()
            context.unroute_all(behavior='ignoreErrors')
            context.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--chromium', required=True)
    args = parser.parse_args()
    if os.environ.get('SELFOS_PLAYWRIGHT_PATH'):
        sys.path.insert(0, os.environ['SELFOS_PLAYWRIGHT_PATH'])
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.chromium, headless=True)
        try:
            print(json.dumps([run_case(browser, locale) for locale in ('en', 'zh-CN')]))
        finally:
            browser.close()


if __name__ == '__main__':
    main()
