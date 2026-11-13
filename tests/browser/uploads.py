"""Upload UI acceptance with synthetic files, authenticated loopback and fixture model."""
import argparse
import json
import os
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path


def run_case(browser, output, locale):
    from integration_fixture import ModelFixture
    from selfos.security.auth import AuthManager
    from selfos.web.rendering.dashboard import generate_dashboard, _I18N
    from selfos.storage.uploads import list_documents
    import selfos.web.server as runtime
    with tempfile.TemporaryDirectory(prefix='selfos-upload-ui-') as directory, ModelFixture() as model:
        root = Path(directory)
        vault = root / 'vault'
        vault.mkdir()
        auth = AuthManager(root, vault, directory=root / 'auth')
        auth.setup('Synthetic upload password')
        (vault / 'PROFILE.md').write_text('- Preferred name: Example User', encoding='utf-8')
        (root / '.selfos-model.json').write_text(json.dumps(dict(provider='openai', model='fixture-model',
            base_url=model.base_url, api_key='synthetic-fixture-key', proxy_mode='direct', proxy_url='')), encoding='utf-8')
        runtime.ROOT, runtime.VAULT = root, vault
        runtime.DASHBOARD = generate_dashboard(vault, scores={key: 6 for key in _I18N})
        runtime.KNOWLEDGE_RUN.clear()
        runtime.KNOWLEDGE_RUN.update(stop_file=None, process=None, job_id=None, phase='idle', saved=set(), total=0, last_line='', result=None)
        class Handler(runtime.Handler):
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.auth = auth
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{server.server_port}'
        context = browser.new_context(viewport=dict(width=1280 if locale == 'en' else 390, height=900))
        context.add_init_script('localStorage.setItem("selfos-lang",' + json.dumps(locale) + ');localStorage.setItem("selfos-theme",' + json.dumps('light' if locale == 'en' else 'dark') + ');')
        context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url + '/') else route.abort())
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.set_default_timeout(10000)
        try:
            page.goto(url)
            page.locator('#auth-password').fill('Synthetic upload password')
            page.locator('#auth-submit').click()
            page.locator('#uploads-open').wait_for(state='visible')
            page.locator('#uploads-open').focus()
            page.keyboard.press('Enter')
            page.locator('#uploads-dialog').wait_for(state='visible')
            first = dict(name='<script>.md', mimeType='text/markdown', buffer=b'\xef\xbb\xbfWe are building a synthetic reliable import project. api_key=SyntheticSecret\nUse immutable originals and source links.')
            second = dict(name='decisions.txt', mimeType='text/plain', buffer=b'Synthetic project decisions: incremental indexing and recoverable backups.')
            page.locator('#uploads-files').set_input_files([first, second])
            page.wait_for_function("document.querySelectorAll('#uploads-queue [data-upload-status=uploaded]').length===2")
            assert len(list_documents(vault)['items']) == 2
            assert model.requests == []
            assert page.locator('#uploads-queue script').count() == 0
            rows = list_documents(vault)['items']
            source = next(row for row in rows if row['original_filename'] == '<script>.md')
            assert (vault / source['path']).read_bytes() == first['buffer']
            selected = page.locator('#uploads-list input:checked').count()
            page.evaluate('window.selfosI18n.setLocale("zh-CN")')
            assert page.locator('#uploads-list input:checked').count() == selected
            page.evaluate('window.selfosI18n.setLocale(' + json.dumps(locale) + ')')
            page.locator('#uploads-list [data-upload-view]').first.click()
            page.locator('#uploads-source-text').wait_for(state='visible')
            assert 'SyntheticSecret' not in page.locator('#uploads-source-text').inner_text()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.locator('#uploads-source-close').click()
            page.locator('#uploads-preview').click()
            page.locator('#uploads-organize:not([disabled])').wait_for()
            assert model.requests == []
            page.locator('#uploads-dialog').screenshot(path=str(output / (locale + '-upload.png')))
            page.locator('#uploads-organize').click()
            page.wait_for_function("document.getElementById('progress-done-btn').style.display!=='none'", timeout=40000)
            assert model.requests
            assert {source['document_id'] for source in json.loads((vault / '.knowledge_pipeline.json').read_text(encoding='utf-8'))['sources'].values()} == {row['id'] for row in rows}
            page.locator('#progress-modal').evaluate("node=>node.classList.remove('open')")
            page.locator('#uploads-open').click()
            page.locator('#uploads-files').set_input_files(first)
            page.wait_for_function("document.querySelector('#uploads-queue [data-upload-status=duplicate]')!==null")
            assert len(list_documents(vault)['items']) == 2
            calls = len(model.requests)
            page.locator('#uploads-preview').click()
            page.wait_for_function("document.getElementById('uploads-preview').disabled===false")
            assert page.locator('#uploads-organize').is_disabled()
            assert len(model.requests) == calls
            # Drop uses the same bounded queue; eleven files are rejected locally.
            page.evaluate("""() => {const transfer=new DataTransfer();for(let i=0;i<11;i++)transfer.items.add(new File(['Synthetic drop '+i], 'file'+i+'.txt',{type:'text/plain'}));document.getElementById('uploads-drop').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer}));}""")
            assert len(list_documents(vault)['items']) == 2
            # Hold the second XHR before network send to deterministically test abort.
            page.evaluate("""() => {const Native=XMLHttpRequest;window.uploadAttempts=0;window.uploadHeld=null;window.XMLHttpRequest=function(){const xhr=new Native();const send=xhr.send.bind(xhr),abort=xhr.abort.bind(xhr);xhr.send=function(body){if(++window.uploadAttempts===2){window.uploadHeld=xhr;return;}send(body);};xhr.abort=function(){if(window.uploadHeld===xhr){if(xhr.onabort)xhr.onabort(new Event('abort'));window.uploadHeld=null;}else abort();};return xhr;};}""")
            page.locator('#uploads-files').set_input_files([dict(name='kept.txt', mimeType='text/plain', buffer=b'Synthetic locally retained file.'),
                dict(name='cancelled.txt', mimeType='text/plain', buffer=b'Synthetic cancelled file.'),
                dict(name='queued.txt', mimeType='text/plain', buffer=b'Synthetic queued file.')])
            page.wait_for_function('window.uploadHeld!==null')
            page.locator('#uploads-cancel').click()
            page.wait_for_function("document.querySelectorAll('#uploads-queue [data-upload-status=interrupted]').length===2")
            assert page.evaluate('window.uploadAttempts') == 2
            assert len(list_documents(vault)['items']) == 3
            assert len(model.requests) == calls
            # Selection capacity is separate from each upload queue's capacity.
            page.locator('#uploads-files').set_input_files([
                dict(name=f'additional-{index}.txt', mimeType='text/plain', buffer=f'Synthetic additional context {index}.'.encode())
                for index in range(9)])
            page.wait_for_function("document.querySelectorAll('#uploads-queue [data-upload-status=uploaded]').length===9")
            page.wait_for_function("document.getElementById('uploads-preview').disabled===false")
            assert len(list_documents(vault)['items']) == 12
            assert page.locator('#uploads-list input:checked').count() == 10, page.locator('#uploads-list').inner_text()
            excess_id = page.locator('#uploads-list input:not(:checked)').first.evaluate("node=>node.closest('.uploads-row').querySelector('button').dataset.uploadView")
            excess = page.locator(f'#uploads-list .uploads-row:has(button[data-upload-view="{excess_id}"]) input')
            excess.click()
            assert not excess.is_checked()
            assert page.locator('#uploads-list input:checked').count() == 10
            page.locator('#uploads-list input:checked').first.click()
            excess.click()
            assert excess.is_checked() and page.locator('#uploads-list input:checked').count() == 10
            assert len(model.requests) == calls
            auth.sessions.clear()
            page.locator('#uploads-files').set_input_files(dict(name='expired.txt', mimeType='text/plain', buffer=b'Synthetic expired session.'))
            page.wait_for_function("document.querySelector('#uploads-queue [data-upload-status=login_required]')!==null")
            assert len(list_documents(vault)['items']) == 12
            assert errors == [], errors
            return dict(locale=locale, admitted=12, model_calls=len(model.requests), cancelled_queue=2, selection_limit=10)
        finally:
            context.close()
            marker = runtime.KNOWLEDGE_RUN.get('stop_file')
            if marker:
                marker.touch()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--chromium', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('SELFOS_PLAYWRIGHT_PATH'):
        sys.path.insert(0, os.environ['SELFOS_PLAYWRIGHT_PATH'])
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
    from playwright.sync_api import sync_playwright
    args.output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.chromium, headless=True)
        try:
            result = [run_case(browser, args.output, locale) for locale in ('en', 'zh-CN')]
        finally:
            browser.close()
    print(json.dumps(result))


if __name__ == '__main__':
    main()
