"""Explicit synthetic first-run Chromium validation with the real CLI/SSE."""
import argparse
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path


def run_case(browser, output, locale, package):
    from integration_fixture import create_profile, ModelFixture
    from selfos.security.auth import AuthManager
    from selfos.web.rendering.dashboard import generate_dashboard
    import selfos.sources.selection as selection
    import selfos.web.server as runtime
    with tempfile.TemporaryDirectory(prefix='selfos-onboarding-') as directory, ModelFixture() as model:
        root = Path(directory)
        vault = root / 'vault'
        vault.mkdir()
        auth = AuthManager(root, vault, directory=root / 'auth')
        auth.setup('Synthetic onboarding password')
        profile = create_profile(root)
        vault = root / 'vault'
        (vault / '.knowledge_pipeline.json').unlink()
        selection.local_roots = lambda: [root / 'missing-default-source']
        (root / '.selfos-model.json').write_text(json.dumps({'provider': 'openai', 'model': 'fixture-model',
            'base_url': model.base_url, 'api_key': 'synthetic-fixture-key', 'proxy_mode': 'direct', 'proxy_url': ''}), encoding='utf-8')
        credentials = (root / '.selfos-model.json').read_bytes()
        runtime.ROOT = root
        runtime.VAULT = vault
        runtime.DASHBOARD = generate_dashboard(vault)
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
        context = browser.new_context(viewport={'width': 1280 if locale == 'en' else 390, 'height': 900}, reduced_motion='reduce' if locale == 'zh-CN' else 'no-preference')
        context.add_init_script('localStorage.setItem("selfos-lang",' + json.dumps(locale) + ');localStorage.setItem("selfos-theme",' + json.dumps('dark' if locale == 'zh-CN' else 'light') + ');')
        context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url + '/') else route.abort())
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.set_default_timeout(10000)
        try:
            page.goto(url)
            page.locator('#auth-password').fill('Synthetic onboarding password')
            page.locator('#auth-submit').click()
            page.locator('#onboarding-welcome').wait_for(state='visible')
            assert model.requests == []
            page.locator('#onboarding-welcome button').click()
            page.locator('#onboarding-next').click()
            page.locator('#onboarding-roots').fill(str(profile['source_root']) + chr(10) + str(profile['ui_sources']))
            page.locator('#onboarding-exclusions').fill(str(profile['ui_sources']))
            page.evaluate('window.selfosI18n.setLocale("zh-CN")')
            assert page.locator('#onboarding-roots').input_value().startswith(str(profile['source_root']))
            page.evaluate('window.selfosI18n.setLocale(' + json.dumps(locale) + ')')
            page.locator('#onboarding-save-sources').click()
            page.locator('#onboarding-next').click()
            if locale == 'en':
                page.locator('#onboarding-dialog button[onclick="onboardingConfigureModel()"]').click()
                page.locator('#model-name').filter().wait_for()
                model.fail_test = True
                with page.expect_response(lambda response: '/__model_test__' in response.url) as failing:
                    page.locator('#model-settings button[onclick="saveModelSettings(true)"]').click()
                assert failing.value.status == 502
                model.fail_test = False
                with page.expect_response(lambda response: '/__model_test__' in response.url) as passing:
                    page.locator('#model-settings button[onclick="saveModelSettings(true)"]').click()
                assert passing.value.status == 200
                assert json.loads((root / '.selfos-model.json').read_text())['api_key'] == 'synthetic-fixture-key'
                credentials = (root / '.selfos-model.json').read_bytes()
                page.locator('#model-settings button[data-i18n="ui.model.close"]').click()
                page.locator('#onboarding-dialog').wait_for(state='visible')
            page.locator('#onboarding-next').click()
            calls_before_sample = len(model.requests)
            page.locator('#onboarding-preview').click()
            page.locator('#onboarding-start:not([disabled])').wait_for()
            assert len(model.requests) == calls_before_sample
            assert (root / '.selfos-model.json').read_bytes() == credentials
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(output / (locale + '-preview.png')))
            if locale == 'zh-CN':
                model.block_second = True
                model.gate.clear()
            page.locator('#onboarding-start').click()
            if locale == 'zh-CN':
                page.locator('#progress-log').filter(has_text='Organizing session 2').wait_for(timeout=15000)
                assert model.blocked.wait(2), 'Second extraction did not start'
                first_session = model.extraction_sessions[0]
                page.locator('#knowledge-stop-btn').click()
                model.gate.set()
                page.locator('#progress-done-btn').wait_for(state='visible', timeout=45000)
                assert not (vault / '.knowledge_pipeline.json').exists()
                saved_budget = json.loads((vault / '.knowledge_onboarding' / 'budgets' /
                    (json.loads((vault / '.knowledge_onboarding.json').read_text())['preview_id'] + '.json')).read_text())
                assert saved_budget['used'] > 0
                page.reload()
                page.locator('#model-settings-entry button').click()
                page.locator('#app-settings button[data-i18n="onboarding.resume_setup"]').click()
                page.locator('#onboarding-resume-sample:not([disabled])').wait_for()
                page.locator('#onboarding-resume-sample').click()
            page.locator('#progress-done-btn').wait_for(state='visible', timeout=45000)
            assert len(model.requests) - calls_before_sample <= 12
            assert (vault / '.knowledge_pipeline.json').exists()
            if locale == 'zh-CN':
                assert model.extraction_sessions.count(first_session) == 1
            page.reload()
            page.locator('#onboarding-welcome').wait_for(state='hidden')
            page.locator('#kb-list .kb-card').first.click()
            page.locator('#kb-sources button').first.click()
            page.locator('#kb-sources pre').filter(has_text='reliable checkpointed knowledge import').wait_for()
            page.locator('#kb-detail').evaluate('(dialog)=>dialog.close()')
            page.locator('#model-settings-entry button').click()
            page.locator('#app-settings button[data-i18n="onboarding.resume_setup"]').click()
            requests_before = len(model.requests)
            page.locator('#onboarding-more').click()
            page.locator('#onboarding-start:not([disabled])').wait_for()
            assert len(model.requests) == requests_before
            state = json.loads((vault / '.knowledge_onboarding.json').read_text())
            expanded = json.loads((vault / '.knowledge_onboarding' / 'previews' / (state['preview_id'] + '.json')).read_text())
            assert expanded['tier'] == 'more' and expanded['budget_limit'] == 24
            page.locator('#onboarding-skip').click()
            page.locator('#onboarding-dialog').wait_for(state='hidden')
            page.locator('#model-settings-entry button').click()
            page.locator('#app-settings button[data-i18n="onboarding.resume_setup"]').click()
            page.locator('#onboarding-start:not([disabled])').wait_for()
            assert json.loads((vault / '.knowledge_onboarding.json').read_text())['preview_id'] == expanded['id']
            assert len(model.requests) == requests_before
            assert all(path.read_bytes() == original for path, original in profile['original_bytes'].items())
            assert errors == [], errors
            return {'locale': locale, 'passed': True, 'sample_requests': len(model.requests) - calls_before_sample,
                    'connection_tests': calls_before_sample, 'stop_resume': locale == 'zh-CN'}
        finally:
            model.gate.set()
            context.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--package-path', type=Path)
    args = parser.parse_args()
    package = args.package_path.resolve() if args.package_path else Path(__file__).resolve().parents[2] / 'src'
    sys.path.insert(0, str(package))
    args.output.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.browser, headless=True)
        try:
            results = [run_case(browser, args.output, locale, package) for locale in ('en', 'zh-CN')]
            (args.output / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
            print(json.dumps(results))
        finally:
            browser.close()
