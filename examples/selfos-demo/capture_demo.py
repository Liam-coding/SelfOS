"""Verify synthetic pages in a browser and capture their actual SelfOS UI."""
import json
import math
from pathlib import Path
import argparse

ROOT = Path(__file__).resolve().parent
from playwright.sync_api import sync_playwright
from PIL import Image

parser = argparse.ArgumentParser(description='Verify synthetic dashboards and capture screenshots.')
parser.add_argument('--browser', help='Optional Chromium executable; defaults to Playwright Chromium.')
args = parser.parse_args()

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=args.browser, headless=True)
    for locale in ('zh', 'en'):
        page = browser.new_page(viewport={'width':1440, 'height':1080}, device_scale_factor=1.5, reduced_motion='reduce')
        errors=[]
        page.on('pageerror', lambda error:errors.append(str(error)))
        page.goto((ROOT / ('selfos-'+locale+'.html')).as_uri())
        page.locator('#knowledge-count-cards').filter(has_text='5').wait_for()
        page.locator('#kb-list .kb-card').first.wait_for()
        assert page.locator('html').get_attribute('lang') == ('zh' if locale=='zh' else 'en')
        for category, count in [('projects',5),('personal_facts',3),('preferences',4),('lessons',5),('history',4)]:
            page.evaluate('(category)=>window.browseKnowledge(category)', category)
            page.wait_for_function('(count)=>document.querySelectorAll("#kb-list .kb-card").length===count', arg=count)
            assert '(21)' in page.locator('#kb-tabs').inner_text()
        page.locator('#kb-list .kb-card').first.click()
        page.locator('#kb-sources button').first.click()
        page.locator('#kb-sources pre').wait_for()
        assert page.locator('#kb-sources pre').inner_text()
        page.locator('#kb-close').click()
        page.evaluate("window.browseKnowledge('projects')")
        page.wait_for_function('document.querySelectorAll("#kb-list .kb-card").length===5')
        page.evaluate('window.scrollTo(0,0)')
        page.locator('#chat-panel').evaluate('(node)=>node.style.visibility="hidden"')
        page.locator('#knowledge-library').evaluate('(node)=>node.style.outline="none"')
        page.locator('#kb-heading').evaluate('(node)=>node.blur()')
        page.screenshot(path=str(ROOT / ('selfos-'+locale+'-full.png')), full_page=True)
        bottom=page.locator('#knowledge-library').bounding_box()
        height=math.ceil(bottom['y']+bottom['height']+28)
        with Image.open(ROOT / ('selfos-'+locale+'-full.png')) as full:
            full.crop((0,0,full.width,round(height*full.width/1440))).save(ROOT / ('selfos-'+locale+'.png'))
        page.set_viewport_size({'width':1040,'height':1000})
        page.locator('#dimension-cards').screenshot(path=str(ROOT / ('selfos-'+locale+'-dimensions.png')))
        page.locator('.knowledge-overall').click()
        assert page.evaluate('location.hash') == '#dimension-cards'
        assert not errors, errors
        print(locale, 'all five categories, exact original source, Overall navigation and screenshots passed')
        page.close()
    browser.close()
