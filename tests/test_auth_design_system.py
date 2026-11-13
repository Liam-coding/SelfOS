"""Synthetic browser coverage for shared controls and theme accessibility."""
import os
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
import pytest


def _contrast(first, second, backdrop='rgb(255, 255, 255)'):
    import re
    def rgba(color):
        values=[float(v) for v in re.findall(r'[0-9.]+',color)]
        return values[:3]+[values[3] if len(values)>3 else 1]
    def blend(top, bottom):
        return [top[i]*top[3]+bottom[i]*(1-top[3]) for i in range(3)]+[1]
    background=blend(rgba(second),rgba(backdrop))
    foreground=blend(rgba(first),background)
    def luminance(color):
        rgb=[v/255 for v in color[:3]]
        linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]
        return sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))
    a,b=sorted((luminance(foreground),luminance(background)))
    return (b+.05)/(a+.05)


@pytest.mark.parametrize('locale,width,theme', [('en',1280,'light'),('en',390,'dark'),('zh-CN',1280,'dark'),('zh-CN',390,'light')])
def test_shared_surfaces_preserve_workflows_and_accessibility(tmp_path, monkeypatch, locale, width, theme):
    playwright=pytest.importorskip('playwright.sync_api')
    from tests.browser.integration_fixture import create_profile
    from selfos.security.auth import AuthManager
    from selfos.web.rendering.dashboard import generate_dashboard
    import selfos.web.server as runtime
    chrome=Path(os.environ.get('SELFOS_CHROME','C:/Users/I748319/.cache/puppeteer/chrome/win64-135.0.7049.95/chrome-win64/chrome.exe'))
    if not chrome.exists():pytest.skip('Synthetic Chromium unavailable')
    (tmp_path/'vault').mkdir()
    auth=AuthManager(tmp_path,tmp_path/'vault',directory=tmp_path/'auth')
    auth.setup('Synthetic style password')
    profile=create_profile(tmp_path)
    from selfos.sources.selection import save_sources
    save_sources(tmp_path/'vault',{'roots':[str(profile['source_root']),str(profile['ui_sources'])],'exclusions':[]})
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    monkeypatch.setattr(runtime,'VAULT',tmp_path/'vault')
    monkeypatch.setattr(runtime,'DASHBOARD',generate_dashboard(runtime.VAULT))
    class Handler(runtime.Handler):
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.auth=auth
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url=f'http://127.0.0.1:{server.server_port}'
    try:
        with playwright.sync_playwright() as p:
            browser=p.chromium.launch(executable_path=str(chrome),headless=True)
            context=browser.new_context(viewport={'width':width,'height':900},reduced_motion='reduce')
            context.add_init_script(f'localStorage.setItem("selfos-lang","{locale}");localStorage.setItem("selfos-theme","{theme}")')
            context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(url+'/') else route.abort())
            page=context.new_page();errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            def check_surface(name, selector):
                target=page.locator(selector);target.wait_for(state='visible')
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.keyboard.press('Tab');target.focus()
                styles=target.evaluate('(e)=>{let s=getComputedStyle(e);return {color:s.color,bg:s.backgroundColor,border:s.borderTopColor,outline:s.outlineStyle,outlineColor:s.outlineColor,transition:s.transitionDuration}}')
                assert target.evaluate('(e)=>e===document.activeElement')
                assert styles['outline']!='none', (name,styles)
                assert all(float(v.rstrip('s'))<=.001 for v in styles['transition'].split(', ')), (name,styles)
                if target.evaluate('(e)=>e.tagName')=='BUTTON':
                    assert _contrast(styles['color'],styles['bg'],page.evaluate('getComputedStyle(document.body).backgroundColor'))>=4.5, (name,styles)
                if target.evaluate('(e)=>e.tagName') in ('INPUT','TEXTAREA','SELECT'):
                    assert _contrast(styles['border'],styles['bg'],page.evaluate('getComputedStyle(document.body).backgroundColor'))>=3, (name,styles)
                page.screenshot(path=str(tmp_path/f'{locale}-{width}-{theme}-{name}.png'))
            page.goto(url)
            check_surface('login','#auth-submit')
            page.locator('#auth-password').fill('Synthetic style password');page.locator('#auth-submit').click()
            page.locator('#model-settings-entry button').wait_for(state='visible')
            check_surface('dashboard','#knowledge-btn')
            page.evaluate('toggleChat()')
            check_surface('chat','#chat-input')
            page.evaluate('toggleChat()')
            page.evaluate('window.browseKnowledge("lessons")')
            check_surface('knowledge-search','#kb-search')
            page.locator('#kb-list .kb-card').first.click()
            check_surface('knowledge-detail','#kb-close')
            page.keyboard.press('Escape')
            page.evaluate('openAppSettings()')
            check_surface('settings','#app-settings .settings-close')
            assert page.locator('#app-settings .settings-signout').evaluate('(e)=>getComputedStyle(e).color') != page.locator('#app-settings .settings-close').evaluate('(e)=>getComputedStyle(e).color')
            page.locator('#app-settings .settings-close').click()
            page.evaluate('openModelSettings()')
            check_surface('model','#model-settings button[type=submit]')
            button=page.locator('#model-settings button[type=submit]')
            button.evaluate('(e)=>e.disabled=true')
            assert button.evaluate('(e)=>getComputedStyle(e).cursor')=='wait'
            assert float(button.evaluate('(e)=>getComputedStyle(e).opacity'))<=.5
            button.evaluate('(e)=>e.disabled=false')
            page.keyboard.press('Escape')
            page.evaluate('openKnowledgeSettings()')
            check_surface('import','#workload-save')
            page.keyboard.press('Escape')
            page.evaluate('openPrivacySettings()')
            check_surface('privacy','#privacy-rules')
            page.keyboard.press('Escape')
            page.evaluate('openOnboarding()')
            check_surface('onboarding','#onboarding-skip')
            page.keyboard.press('Escape')
            page.evaluate('openAppSettings()')
            page.locator('#app-settings [data-i18n="auth.change"]').click()
            check_surface('account','#auth-change button[type=submit]')
            page.locator('#auth-current').fill('Synthetic style password')
            page.locator('#auth-new').fill('Synthetic replacement password')
            page.locator('#auth-new-confirm').fill('Different replacement password')
            page.locator('#auth-change button[type=submit]').click()
            status=page.locator('#auth-change-status')
            assert status.inner_text().strip()
            assert status.inner_text()==page.evaluate('selfosI18n.t("auth.mismatch")')
            page.evaluate('selfosI18n.setLocale(selfosI18n.locale==="en"?"zh-CN":"en")')
            assert status.inner_text()==page.evaluate('selfosI18n.t("auth.mismatch")')
            colors=status.evaluate('(e)=>({text:getComputedStyle(e).color,bg:getComputedStyle(e.closest("dialog")).backgroundColor})')
            assert _contrast(colors['text'],colors['bg'])>=4.5
            assert page.locator('#auth-change button[type=submit]').is_enabled()
            assert errors==[],errors
            context.close();browser.close()
    finally:
        server.shutdown();server.server_close()
