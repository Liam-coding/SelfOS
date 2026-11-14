"""Real authenticated synthetic history UI: no model or personal vault."""
import argparse
import hashlib
import json
import sys
import threading
import uuid
from pathlib import Path
from http.server import ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'src'))

def run(output,browser_path):
    from playwright.sync_api import sync_playwright,expect
    import selfos.web.server as runtime
    from selfos.web.rendering.dashboard import generate_dashboard
    from selfos.security.auth import AuthManager
    from selfos.app.change_publication import publish_changes
    from selfos.storage.pipeline import restore_pipeline_backup
    from tests.test_knowledge_corrections import record,state
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=browser_path,headless=True)
        for locale in ('en','zh-CN'):
            app=output/(locale+'-'+uuid.uuid4().hex[:8]);vault=app/'vault';vault.mkdir(parents=True,exist_ok=True)
            auth=AuthManager(app,vault,directory=app/'auth');auth.setup('synthetic history password')
            path=vault/'.knowledge_uploads/originals/synthetic.txt';path.parent.mkdir(parents=True)
            raw=b'I prefer concise explanations. I prefer brief explanations.';path.write_bytes(raw)
            source={'source':'uploaded_file','path':str(path.relative_to(vault)),'original_filename':'Synthetic conversation.txt',
                'role':'user','timestamp':'2026-01-01T00:00:00Z','content_sha256':hashlib.sha256(raw).hexdigest()}
            generated=state(record(),record('brief','m2'));generated['sources']={'m1':source,'m2':source}
            publish_changes(vault,{'.knowledge_pipeline.json':json.dumps(generated).encode()},'20261114T100000-123456abcdef',1,kind='import')
            runtime.ROOT=app;runtime.VAULT=vault;runtime.DASHBOARD=generate_dashboard(vault)
            class Handler(runtime.Handler):
                def log_message(self,*args):pass
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.auth=auth
            threading.Thread(target=server.serve_forever,daemon=True).start()
            url=f'http://127.0.0.1:{server.server_port}'
            context=browser.new_context(viewport={'width':1280 if locale=='en' else 390,'height':900 if locale=='en' else 844})
            context.add_cookies([{'name':'selfos_session','value':auth.login('synthetic history password'),'url':url,'sameSite':'Strict'}])
            context.add_init_script('localStorage.setItem("selfos-lang",'+json.dumps(locale)+');localStorage.setItem("selfos-theme",'+json.dumps('light' if locale=='en' else 'dark')+');')
            page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            def rows():return context.request.get(url+'/__knowledge__?category=preferences').json()['items']
            def correct(body):
                response=context.request.post(url+'/__knowledge_correct__',data=body)
                assert response.ok,response.text()
                return response.json()
            try:
                page.goto(url);page.locator('#knowledge-changes-entry').click();expect(page.locator('.changes-operation')).to_have_count(1)
                page.locator('.changes-operation').click();expect(page.locator('.changes-change')).to_have_count(2)
                row=next(row for row in rows() if row['title']=='concise')
                edited=correct({'action':'edit','ids':[row['id']],'patch':{'value':'balanced','text':'Balanced <img src=x onerror=alert(1)> explanations'}})
                page.locator('#changes-restart').click();expect(page.locator('.changes-operation')).to_have_count(2)
                page.locator('[data-event="'+edited['backup_id']+':1"]').click()
                expect(page.locator('.changes-change')).to_have_count(2)
                expect(page.locator('#changes-before-after')).to_contain_text('Balanced <img')
                assert page.locator('#changes-before-after img').count()==0
                page.locator('.changes-values button').first.click();expect(page.locator('#changes-source-text')).to_contain_text('I prefer concise')
                page.evaluate('window.selfosI18n.setLocale('+json.dumps('zh-CN' if locale=='en' else 'en')+')')
                expect(page.locator('.changes-operation')).to_have_count(2)
                expect(page.locator('.changes-operation p').first).not_to_be_empty()
                page.evaluate('window.selfosI18n.setLocale('+json.dumps(locale)+')')
                row=next(row for row in rows() if row['title']=='balanced')
                deleted=correct({'action':'delete','ids':[row['id']]})
                correct({'action':'undo','action_id':deleted['action_id']})
                merged=correct({'action':'merge','ids':[row['id'] for row in rows()],
                    'patch':{'value':'balanced','text':'Merged explanation preference'}})
                page.locator('#changes-restart').click();expect(page.locator('.changes-operation')).to_have_count(5)
                entry=page.locator('[data-event="'+merged['backup_id']+':1"]');entry.click()
                expect(page.locator('.changes-change')).to_have_count(1)
                expect(page.locator('#changes-before-after')).to_contain_text('Merged explanation preference')
                assert page.locator('.changes-values>div').first.locator('button').count()==2
                restore_pipeline_backup(vault,merged['backup_id'])
                entry.click();expect(page.locator('#changes-status')).to_contain_text('Restart' if locale=='en' else '重新加载')
                page.locator('#changes-restart').click();expect(page.locator('.changes-operation')).to_have_count(6)
                expect(page.locator('[data-event="'+merged['backup_id']+':1"]')).to_contain_text('Reverted' if locale=='en' else '已恢复')
                page.locator('#changes-conflicts').check();expect(page.locator('.changes-operation')).to_have_count(5)
                page.locator('#changes-conflicts').uncheck();expect(page.locator('.changes-operation')).to_have_count(6)
                page.locator('.changes-operation').first.click();expect(page.locator('.changes-change')).to_have_count(1)
                assert page.evaluate('document.querySelector("#knowledge-changes").scrollWidth<=document.querySelector("#knowledge-changes").clientWidth+1')
                assert path.read_bytes()==raw and not errors,errors
                page.screenshot(path=str(output/('changes-'+locale+'.png')))
                current=json.loads((vault/'.knowledge_pipeline.json').read_text())
                card={'project_id':'synthetic-project','title':'Synthetic project','intent':'Stable project goal','domain':'work',
                      'status':'in_progress','source_ids':['m1'],'decisions':[],'blockers':[],'next_steps':[]}
                current['cards']={'synthetic-project':card}
                publish_changes(vault,{'.knowledge_pipeline.json':json.dumps(current).encode()},'20261114T100001-123456abcdef',1,kind='import')
                current['cards']['synthetic-project']={**card,'status':'blocked','blockers':['Awaiting synthetic access'],
                    'decisions':['Keep immutable originals'],'next_steps':['Review source permissions']}
                publish_changes(vault,{'.knowledge_pipeline.json':json.dumps(current).encode()},'20261114T100002-123456abcdef',1,kind='import')
                page.locator('#changes-restart').click();expect(page.locator('.changes-operation')).to_have_count(8)
                page.locator('[data-event="20261114T100002-123456abcdef:1"]').click()
                expect(page.locator('.changes-change')).to_have_count(1)
                expect(page.locator('.changes-values>div').first).to_contain_text('In progress' if locale=='en' else '进行中')
                expect(page.locator('.changes-values>div').last).to_contain_text('Blocked' if locale=='en' else '存在阻碍')
                expect(page.locator('.changes-values>div').last).to_contain_text('Awaiting synthetic access')
                expect(page.locator('.changes-values>div').last).to_contain_text('Review source permissions')
                page.locator('#changes-close').click()
                project=context.request.get(url+'/__knowledge__?category=projects').json()['items'][0]
                page.evaluate('window.openKnowledgeDetail('+json.dumps(project['id'])+')')
                page.locator('[data-knowledge-changes]').click()
                expect(page.locator('.changes-change')).to_have_count(1)
                expect(page.locator('#changes-before-after')).to_contain_text('Awaiting synthetic access')
                page.locator('#changes-close').click()
                page.evaluate('window.selfosUI.module("settings").open()')
                page.locator('[data-selfos-action="settings.privacy"]').click()
                expect(page.locator('#privacy-destination')).not_to_be_empty()
                page.locator('#privacy-audit').select_option('recent')
                page.locator('#privacy-audit-recent').fill('2')
                page.locator('[data-selfos-action="privacy.export"]').click()
                expect(page.locator('#privacy-download')).to_be_visible()
                expect(page.locator('#privacy-status')).to_contain_text('2')
                page.evaluate('window.selfosUI.teardown();window.selfosUI.init(document);window.selfosUI.init(document)')
                expect(page.locator('#privacy-audit')).to_have_value('recent')
                expect(page.locator('#privacy-audit-recent')).to_have_value('2')
                expect(page.locator('#privacy-download')).to_be_visible()
                with page.expect_download() as download_info:
                    page.locator('#privacy-download').click()
                exported=json.loads(Path(download_info.value.path()).read_text(encoding='utf-8'))
                assert exported['audit_summary']['operations']==2
                assert exported['audit_summary']['earlier_history_omitted']
                assert path.read_bytes()==raw
                assert not errors,errors
                print(locale,'history/corrections/restoration, scoped navigation, audit export preview/remount/download passed')
            finally:
                context.close();server.shutdown();server.server_close()
        browser.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--browser',required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True);run(args.output.resolve(),args.browser)
