"""Exercise installed dashboard UI against synthetic, intercepted HTTP responses."""
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

if len(sys.argv) != 4:
    raise SystemExit('Usage: python tools/verify_browser.py installed-dir output-dir chromium|webkit')
installed=Path(sys.argv[1]).resolve()
output=Path(sys.argv[2]).resolve();output.mkdir(parents=True,exist_ok=True)
engine=sys.argv[3]
if engine not in ('chromium','webkit'):raise SystemExit('Unsupported browser engine')
sys.path.insert(0,str(installed))
from selfos.web.rendering import dashboard
assert Path(dashboard.__file__).resolve().is_relative_to(installed)

item={'id':'fixture','category':'projects','title':'Fixture project','summary':'Synthetic knowledge only.',
      'date':'2026-11-12','source_count':1,'status':'in_progress','decisions':[],
      'blockers':[],'next_steps':[],'conflict':False}
config={'provider':'anthropic','model':'fixture-model','base_url':'https://api.anthropic.com',
        'proxy_mode':'direct','proxy_url':'','proxy_source':'direct','effective_proxy':{},'has_api_key':False}
with tempfile.TemporaryDirectory() as folder:
    vault=Path(folder)/'vault';vault.mkdir()
    html=dashboard.generate_dashboard(vault).read_text(encoding='utf-8')
    def respond(route):
        path=urlsplit(route.request.url).path
        if path=='/':return route.fulfill(content_type='text/html',body=html)
        if path=='/__model_settings__':data=config
        elif path=='/__knowledge_settings__':data={'settings':{'domains':['work'],'detail':'balanced'},'counts':{},'saved_checkpoints':0}
        elif path=='/__knowledge__':data={'items':[item],'total':1}
        elif path=='/__knowledge_item__':data={'item':item,'sources':[{'id':'source-fixture','source':'fixture','role':'user','file':'fixture.jsonl'}],'source_count':1}
        elif path=='/__knowledge_source__':data={'text':'I am building a fixture project.'}
        else:data={}
        route.fulfill(content_type='application/json',body=json.dumps(data))
    with sync_playwright() as playwright:
        options={'headless':True}
        if os.environ.get('SELFOS_BROWSER_EXECUTABLE'):options['executable_path']=os.environ['SELFOS_BROWSER_EXECUTABLE']
        browser=getattr(playwright,engine).launch(**options)
        for name,width,height in [('desktop',1440,900),('mobile',390,740)]:
            page=browser.new_page(viewport={'width':width,'height':height},reduced_motion='reduce')
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.route('**/*',respond)
            page.goto('http://fixture.test/')
            page.locator('#kb-list .kb-card').first.wait_for()
            assert page.locator('html').get_attribute('lang')=='en'
            page.evaluate('toggleTheme()')
            assert 'dark' in page.locator('body').get_attribute('class')
            page.locator('#model-settings-entry button').click()
            page.locator('#settings-language').select_option('zh-CN')
            assert page.locator('html').get_attribute('lang')=='zh'
            assert page.evaluate('window.selfosI18n.locale')=='zh-CN'
            page.locator('#settings-language').select_option('en')
            page.locator('#app-settings button').filter(has_text='Model and network').click()
            page.locator('#model-name').wait_for()
            page.wait_for_function("document.getElementById('model-name').value==='fixture-model'")
            page.locator('#model-name').fill('unsaved-fixture')
            page.evaluate("window.selfosI18n.setLocale('zh')")
            assert page.locator('#model-name').input_value()=='unsaved-fixture'
            page.evaluate("window.selfosI18n.setLocale('en')")
            page.locator('#model-settings button').filter(has_text='Close').click()
            page.locator('#kb-search').fill('fixture')
            page.locator('#kb-list .kb-card').first.click()
            page.locator('#kb-sources').get_by_role('button',name='Read original source',exact=True).click()
            page.locator('#kb-sources pre').filter(has_text='I am building a fixture project.').wait_for()
            page.evaluate("window.originalSourceNode=document.querySelector('#kb-sources pre');window.selfosI18n.setLocale('zh')")
            assert page.evaluate("originalSourceNode===document.querySelector('#kb-sources pre')")
            assert page.locator('#kb-sources pre').inner_text()=='I am building a fixture project.'
            page.evaluate("window.selfosI18n.setLocale('en')")
            page.locator('.kb-close').click()
            page.evaluate('openKnowledgeSettings()')
            page.locator('#knowledge-domains input').first.wait_for()
            page.locator('#knowledge-custom').fill('music')
            page.locator('#knowledge-settings button').filter(has_text='Close').click()
            page.screenshot(path=str(output/f'{engine}-{name}.png'),full_page=True)
            assert not errors, errors
            print(engine,name,'settings, locale/theme, knowledge search/detail/source passed')
            page.close()
        browser.close()
