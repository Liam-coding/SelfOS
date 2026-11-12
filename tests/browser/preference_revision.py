"""Real localized browser verification using synthetic revision sources only."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))


def run(output,browser_path=None):
    output=output.resolve()
    from selfos.knowledge.records import validate_record, merge_records
    from selfos.knowledge.settings import DEFAULT_SETTINGS
    from selfos.app.library import list_knowledge, knowledge_detail, knowledge_timeline
    from selfos.web.rendering.dashboard import generate_dashboard
    from playwright.sync_api import sync_playwright
    spec=importlib.util.spec_from_file_location('demo_builder',ROOT/'examples/selfos-demo/build_demo.py')
    demo=importlib.util.module_from_spec(spec);spec.loader.exec_module(demo)
    fixture=json.loads((ROOT/'examples/selfos-demo/fixture.json').read_text(encoding='utf-8'))
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=browser_path,headless=True)
        for locale in ('en','zh'):
            demo.build(fixture,locale,output)
            vault=output/locale/'vault'
            state=json.loads((vault/'.knowledge_pipeline.json').read_text(encoding='utf-8'))
            for identity,value,quote,at,previous,effective in [
                ('old','concise','I prefer concise explanations.','2026-01-01T10:00:00Z',None,None),
                ('new','detailed','From 2026-02-01 I change concise explanations to detailed explanations.','2026-02-03T10:00:00Z','concise','2026-02-01'),
                ('planned','brief','From 2099-01-01 I change detailed explanations to brief explanations.','2026-03-03T10:00:00Z','detailed','2099-01-01')]:
                message={'id':identity,'role':'user','text':quote,'timestamp':at,'source':'codex','path':'synthetic-'+identity+'.jsonl'}
                state['sources'][identity]=message
                raw={'key':'communication.detail','value':value,'text':quote,'scope':'global','kind':'user_fact',
                     'temporal':'current','domain':'personal','source_ids':[identity],'evidence':quote}
                if previous:raw['revision']={'previous_value':previous,'effective_at':effective,'source_id':identity,'evidence':quote}
                merge_records(state,'preferences',[validate_record(raw,{'messages':[message]})],DEFAULT_SETTINGS)
            (vault/'.knowledge_pipeline.json').write_text(json.dumps(state),encoding='utf-8')
            user={'id':'fact-user','role':'user','text':'I work as a designer.','timestamp':'2026-01-01T10:00:00Z','source':'codex'}
            context={'id':'fact-context','role':'assistant','text':'That helps the project.','timestamp':'2026-01-02T10:00:00Z','source':'codex'}
            state['sources'].update({user['id']:user,context['id']:context})
            raw={'key':'employment.role','value':'designer','text':'I work as a designer.','scope':{'type':'activity','id':'work'},
                 'kind':'user_fact','domain':'personal','source_ids':[user['id'],context['id']],'evidence':user['text']}
            merge_records(state,'personal_facts',[validate_record(raw,{'messages':[user,context]})],DEFAULT_SETTINGS)
            (vault/'.knowledge_pipeline.json').write_text(json.dumps(state),encoding='utf-8')
            page_text=generate_dashboard(vault,scores=fixture['scores']).read_text(encoding='utf-8')
            listing=list_knowledge(vault,limit=200)
            payload={'listing':listing,'details':{r['id']:knowledge_detail(vault,r['id']) for r in listing['items']},
                     'timelines':{r['id']:knowledge_timeline(vault,r['id']) for r in listing['items'] if r['category']=='projects'},
                     'texts':{i:s['text'] for i,s in state['sources'].items()},'counts':listing['counts']}
            encoded=json.dumps(payload,ensure_ascii=True).replace('<',chr(92)+'u003c')
            adapter=(ROOT/'examples/selfos-demo/demo-adapter.js').read_text(encoding='utf-8').replace('__DEMO_DATA__',encoded).replace('__DEMO_LOCALE__','en' if locale=='en' else 'zh-CN')
            destination=output/('revision-'+locale+'.html')
            destination.write_text(page_text.replace('<head>','<head><script>'+adapter+'</script>',1),encoding='utf-8')
            page=browser.new_page();errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(destination.as_uri());page.locator('#kb-list .kb-card').first.wait_for()
            page.evaluate("window.browseKnowledge('personal_facts')")
            page.locator('#kb-list .kb-card').filter(has_text='I work as a designer.').first.click()
            page.locator('#kb-sources').get_by_text('Direct supporting evidence' if locale=='en' else '直接支持证据',exact=True).wait_for()
            page.locator('#kb-sources').get_by_text('Context reference; does not support the personal claim' if locale=='en' else '上下文引用，不支持该个人属性',exact=True).wait_for()
            page.locator('#kb-close').click()
            page.evaluate("window.browseKnowledge('preferences')")
            page.locator('#kb-list .kb-card').filter(has_text='From 2026-02-01').first.click()
            page.locator('#kb-detail-content').get_by_text('Effective from: 2026-02-01' if locale=='en' else '生效日期：2026-02-01',exact=True).wait_for()
            page.locator('#kb-detail-content pre').first.wait_for()
            page.locator('#kb-sources button').first.click();page.locator('#kb-sources pre').wait_for()
            page.locator('#kb-close').click();page.evaluate("window.browseKnowledge('history')")
            page.locator('#kb-list .kb-card').filter(has_text='From 2099-01-01').first.click()
            page.locator('#kb-detail-content').get_by_text('Planned change; this preference is not active yet.' if locale=='en' else '计划中的变更，这条偏好尚未生效。',exact=True).wait_for()
            assert not errors,errors
            print(locale,'validity, revision evidence, source viewing and planned change passed')
            page.close()
        browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser');parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.output:
        args.output.mkdir(parents=True,exist_ok=True);run(args.output,args.browser)
    else:
        with tempfile.TemporaryDirectory(prefix='selfos-revision-') as temporary:run(Path(temporary),args.browser)
