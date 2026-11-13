"""Real-browser Settings ordering, focus and responsive regression checks."""
import argparse
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path


def run_case(browser, output, locale, width, theme):
    from integration_fixture import create_profile
    from selfos.security.auth import AuthManager
    from selfos.web.rendering.dashboard import generate_dashboard
    import selfos.web.server as runtime
    with tempfile.TemporaryDirectory(prefix='selfos-settings-') as directory:
        root = Path(directory)
        vault = root / 'vault'
        vault.mkdir()
        auth = AuthManager(root, vault, directory=root / 'auth')
        auth.setup('Synthetic settings password')
        create_profile(root)
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
        context = browser.new_context(viewport={'width': width, 'height': 900}, reduced_motion='reduce')
        context.add_init_script('localStorage.setItem("selfos-lang",' + json.dumps(locale) + ');localStorage.setItem("selfos-theme",' + json.dumps(theme) + ');')
        context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url + '/') else route.abort())
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            page.goto(url)
            page.locator('#auth-password').fill('Synthetic settings password')
            page.locator('#auth-submit').click()
            trigger = page.locator('#model-settings-entry button')
            trigger.click()
            dialog = page.locator('#app-settings')
            dialog.wait_for(state='visible')
            order = dialog.locator('select, button').evaluate_all('(nodes)=>nodes.filter(n=>!n.hidden).map(n=>n.id||n.dataset.i18n)')
            assert order == ['settings-language', 'ui.model.model_and_network', 'onboarding.resume_setup', 'auth.change', 'auth.logout', 'ui.model.close'], order
            assert page.locator('#auth-account-buttons').evaluate('(e)=>!!e.closest("section")'), 'Account actions are outside their section'
            assert dialog.locator('footer button').get_attribute('data-i18n') == 'ui.model.close'
            change = dialog.locator('[data-i18n="auth.change"]').bounding_box()
            logout = dialog.locator('[data-i18n="auth.logout"]').bounding_box()
            assert logout['y'] >= change['y'] + change['height'] + 7, 'Account actions crowd together'
            assert dialog.evaluate('(d)=>d.scrollWidth<=d.clientWidth'), 'Settings overflows horizontally'
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.locator('#settings-language').focus()
            for key in order[1:]:
                page.keyboard.press('Tab')
                assert page.evaluate('document.activeElement.dataset.i18n') == key
            page.screenshot(path=str(output / f'{locale}-{width}-{theme}.png'))
            page.keyboard.press('Enter')
            dialog.wait_for(state='hidden')
            assert trigger.evaluate('(e)=>e===document.activeElement'), 'Close did not return focus'
            trigger.click()
            page.keyboard.press('Escape')
            dialog.wait_for(state='hidden')
            assert trigger.evaluate('(e)=>e===document.activeElement'), 'Escape did not return focus'
            trigger.click()
            dialog.locator('[data-i18n="auth.change"]').click()
            page.locator('#auth-change').wait_for(state='visible')
            assert not dialog.is_visible()
            assert errors == [], errors
            return {'locale': locale, 'width': width, 'theme': theme, 'passed': True}
        finally:
            context.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
    args.output.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.browser, headless=True)
        try:
            results = [run_case(browser, args.output, locale, width, theme)
                       for locale in ('en', 'zh-CN') for width in (1280, 390) for theme in ('light', 'dark')]
            (args.output / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
            print(json.dumps(results))
        finally:
            browser.close()
