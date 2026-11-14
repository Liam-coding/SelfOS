"""Native browser checks the single composer owner with synthetic answers."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from chromium_fixture import run_chromium


@pytest.mark.parametrize('locale', ['en', 'zh-CN'])
def test_qa_safe_citations_cancel_and_cloned_remount(tmp_path, locale):
    from selfos.web.i18n import runtime
    from selfos.web.rendering.resources import frontend_text
    page = '<html><head>' + runtime() + '</head><body>'
    page += '<script>' + frontend_text('scripts/ui-runtime.js') + '</script>'
    page += '''<div id="chat-panel"><button id="chat-collapse-btn"></button><div id="chat-messages"></div>
      <textarea id="chat-input"></textarea><button id="chat-send" data-selfos-action="chat.send"></button></div>
      <script>window.navigation=[];selfosUI.register('request',()=>({}));selfosUI.register('locale',()=>selfosI18n);
      selfosUI.register('knowledge',()=>({openDetail:async(...args)=>navigation.push(args),readSource:async(...args)=>navigation.push(args)}));</script>'''
    page += '<script>' + frontend_text('scripts/dashboard-chat.js') + '</script><script>selfosUI.init(document);</script></body></html>'
    captured = []
    result = dict(status='answered', answer_kind='model_interpretation', reply='<img src=x onerror=window.hacked=true>',
        references=[dict(id='known', revision='a' * 64, title='Synthetic decision', category='preferences', summary='Balanced explanations',
            evidence='Original concise quotation', user_corrected=True, kind='user_correction', historical=True, conflict=True,
            verified=False, source_scope='project_context', support_review='', source_count=1, source_coverage='complete',
            sources=[dict(id='m1', file='synthetic.jsonl')])],
        inferences=[dict(text='Optional inference', record_ids=['known'], kind='model_inference')])
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def send(self, data, kind='application/json'):
            raw = json.dumps(data).encode() if kind == 'application/json' else data.encode()
            self.send_response(200);self.send_header('Content-Type', kind);self.send_header('Content-Length', str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            if self.path.startswith('/__knowledge_qa_context__'):
                return self.send(dict(projects=[dict(id='alpha', title='Synthetic project')]))
            if self.path.startswith('/__knowledge_qa_citation__'):
                return self.send(dict(id='known', revision='a' * 64))
            self.send(page, 'text/html; charset=utf-8')
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            captured.append((self.path, body))
            self.send(result if self.path == '/__knowledge_qa__' else dict(reply='General conversation reply'))
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    expression = r'''(async()=>{
      const get=id=>document.getElementById(id),assert=(v,m)=>{if(!v)throw Error(m)},wait=async f=>{for(let i=0;i<150;i++){if(f())return;await new Promise(r=>setTimeout(r,20))}throw Error('timeout')};
      selfosI18n.setLocale(LOCALE);const chat=selfosUI.module('chat');chat.open();
      assert(get('chat-mode').value==='knowledge','knowledge is default');
      await wait(()=>get('chat-project').options.length===2);get('chat-project').value='alpha';
      get('chat-input').value='Why this decision?';get('chat-send').click();await wait(()=>document.querySelector('.qa-reference'));
      assert(!document.querySelector('#chat-messages img')&&!window.hacked,'safe model prose');
      assert(get('chat-messages').textContent.includes(selfosI18n.t('qa.correction')),'correction label');
      assert(get('chat-messages').textContent.includes(selfosI18n.t('qa.kind_correction')),'retained evidence kind');
      assert(get('chat-messages').textContent.includes(selfosI18n.t('qa.history')),'history label');
      document.querySelector('[data-qa-detail]').click();await wait(()=>navigation.length===1);assert(navigation[0][0]==='known'&&navigation[0][1]==='a'.repeat(64),'revision passed to detail owner');
      selfosUI.teardown(document);selfosUI.init(document);document.querySelector('[data-qa-detail]').click();await wait(()=>navigation.length===2);
      const originalFetch=fetch;let resolveLate,calls=0;window.fetch=(url,options)=>{if(url==='/__knowledge_qa__'){calls++;return new Promise(r=>resolveLate=r)}return originalFetch(url,options)};
      get('chat-input').value='Pending question';get('chat-send').click();get('chat-input').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));assert(calls===1,'coalesced pending input');
      get('chat-cancel').click();await wait(()=>!chat.busy());resolveLate({ok:true,json:async()=>({...ANSWER,reply:'late answer'})});await new Promise(r=>setTimeout(r,50));assert(!get('chat-messages').textContent.includes('late answer'),'cancel discards late result');window.fetch=originalFetch;
      get('chat-input').value='Preserved draft';selfosUI.teardown(document);get('chat-panel').replaceWith(get('chat-panel').cloneNode(true));selfosUI.init(document);
      assert(get('chat-input').value==='Preserved draft','draft preserved');assert(document.querySelectorAll('#chat-mode').length===1&&document.querySelectorAll('.qa-reference').length===1,'one owner with structured history');
      get('chat-mode').value='conversation';get('chat-mode').dispatchEvent(new Event('change'));get('chat-input').value='General question';get('chat-send').click();await wait(()=>get('chat-messages').textContent.includes('General conversation reply'));
      assert(chat.snapshot().history.every(item=>!item.content.includes('<img')&&!item.content.includes('Why this decision')),'QA excluded from conversation context');
      get('chat-mode').value='knowledge';get('chat-mode').dispatchEvent(new Event('change'));window.fetch=async()=>({ok:false,json:async()=>({code:'qa_unavailable',error:'RAW PRIVATE ERROR'})});
      get('chat-input').value='Failed question';get('chat-send').click();await wait(()=>get('chat-messages').textContent.includes(selfosI18n.t('qa.failed')));selfosI18n.setLocale(LOCALE==='en'?'zh-CN':'en');assert(get('chat-messages').textContent.includes(selfosI18n.t('qa.failed'))&&!get('chat-messages').textContent.includes('RAW PRIVATE'),'localized safe error');window.fetch=originalFetch;
      return 'qa browser verified';
    })()'''.replace('LOCALE', json.dumps(locale)).replace('ANSWER', json.dumps(result))
    try:
        assert 'qa browser verified' in run_chromium(tmp_path, f'http://127.0.0.1:{server.server_port}', expression, width=390)
        assert captured[0][1]['project'] == 'alpha'
        assert captured[-1] == ('/chat', {'messages': [{'role': 'user', 'content': 'General question'}]})
    finally:
        server.shutdown();server.server_close()


def test_full_cached_dashboard_resolves_real_synthetic_original_and_rejects_stale_citation(tmp_path, monkeypatch):
    from selfos.web import server as runtime_server
    from selfos.sources.selection import save_sources
    from selfos.sources.conversations import extract_conversations
    from selfos.web.rendering.dashboard import generate_dashboard
    from selfos.web.rendering.refresh import refresh_dashboard
    app = tmp_path / 'app';vault = app / 'vault';vault.mkdir(parents=True)
    root = tmp_path / 'synthetic sessions';root.mkdir()
    original = 'We selected SQLite because atomic local writes make interrupted imports recoverable.'
    (root / 'session.jsonl').write_text('\n'.join(json.dumps(dict(type='user', timestamp='2026-01-01T10:00:00Z',
        sessionId='synthetic', message=dict(content=original + f' Source {index}.' + ' synthetic padding' * 1600))) for index in range(35)), encoding='utf-8')
    messages = extract_conversations([root]);message = messages[0]
    save_sources(vault, dict(roots=[str(root)], exclusions=[]))
    state = dict(cards={'alpha': dict(project_id='alpha', title='Synthetic importer', intent='Recover interrupted imports',
        status='in_progress', decisions=[original], blockers=[], next_steps=[], source_ids=[m['id'] for m in messages], verified=False)},
        lessons=[], preferences=[], personal_facts=[], sources={m['id']: m for m in messages})
    state_path = vault / '.knowledge_pipeline.json';state_path.write_text(json.dumps(state), encoding='utf-8')
    dashboard = generate_dashboard(vault);page = dashboard.read_text(encoding='utf-8')
    for _ in range(3):
        page = refresh_dashboard(page)
        assert page.count('id="selfos-knowledge-qa"') == 1
        assert page.count('data-selfos-module="chat"') == 1
    dashboard.write_text(page, encoding='utf-8')
    monkeypatch.setattr(runtime_server, 'ROOT', app);monkeypatch.setattr(runtime_server, 'VAULT', vault)
    monkeypatch.setattr(runtime_server, 'DASHBOARD', dashboard)
    def factory(*args):
        def answer(question, rows, feedback=None):
            return dict(status='answered', answer='SQLite supports recoverable atomic writes.',
                record_ids=[rows[0]['record']['id']], inferences=[])
        return answer
    monkeypatch.setattr('selfos.providers.knowledge_qa.answerer_for', factory)
    class Handler(runtime_server.Handler):
        def do_POST(self):
            if self.path == '/fixture-reset':
                state_path.write_text(json.dumps(state), encoding='utf-8')
                return self._send_json(200, {})
            if self.path == '/fixture-mutate':
                updated = json.loads(state_path.read_text(encoding='utf-8'))
                updated['cards']['alpha']['intent'] += ' Changed synthetic purpose'
                state_path.write_text(json.dumps(updated), encoding='utf-8')
                return self._send_json(200, {})
            return super().do_POST()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    expression = r'''(async()=>{
      const get=id=>document.getElementById(id),assert=(v,m)=>{if(!v)throw Error(m)},wait=async f=>{for(let i=0;i<200;i++){if(f())return;await new Promise(r=>setTimeout(r,20))}throw Error('timeout')};
      const originalFetch=fetch,responses=[];let arm=false;window.fetch=async(url,options)=>{const r=await originalFetch(url,options);if(String(url).startsWith('/__knowledge_source__')||String(url).includes('source_offset'))responses.push({url:String(url),data:await r.clone().json()});if(arm&&String(url).startsWith('/__knowledge_item__')){arm=false;await originalFetch('/fixture-mutate',{method:'POST'});}return r;};
      selfosUI.module('chat').open();get('chat-input').value='Why SQLite?';get('chat-send').click();await wait(()=>document.querySelector('[data-qa-source]'));
      assert(get('chat-messages').textContent.includes(selfosI18n.t('qa.status_in_progress')),'current project status');
      document.querySelector('[data-qa-source]').click();await wait(()=>get('kb-detail').open&&get('kb-detail-content').textContent.includes(ORIGINAL));
      await wait(()=>get('kb-detail-content').querySelector('#kb-sources pre')?.textContent.includes(ORIGINAL));
      const originalPage=get('kb-sources').querySelector('pre'),before=originalPage.textContent.length;responses.length=0;await fetch('/fixture-mutate',{method:'POST'});
      originalPage.parentElement.querySelector('[data-selfos-action="knowledge.source"]').click();await wait(()=>responses.some(item=>item.url.includes('offset=24000')&&item.data.code==='knowledge_changed'));
      assert(get('kb-sources').querySelector('pre').textContent.length===before,'stale source text continuation suppressed');await fetch('/fixture-reset',{method:'POST'});
      get('kb-detail').close();document.querySelector('[data-qa-detail]').click();await wait(()=>get('kb-detail').open&&get('kb-more-sources')&&!get('kb-more-sources').hidden);await fetch('/fixture-mutate',{method:'POST'});
      get('kb-more-sources').click();await wait(()=>responses.some(item=>item.url.includes('source_offset')&&item.data.code==='knowledge_changed'));
      get('kb-sources').querySelector('[data-selfos-action="knowledge.source"]').click();await wait(()=>responses.some(item=>item.url.startsWith('/__knowledge_source__')&&item.data.code==='knowledge_changed'));
      assert(!get('kb-sources').querySelector('pre'),'changed original suppressed');get('kb-detail').close();
      document.querySelector('[data-qa-detail]').click();await wait(()=>get('chat-messages').textContent.includes(selfosI18n.t('qa.stale')));
      assert(!get('kb-detail').open,'stale citation did not navigate');
      get('chat-input').value='Why SQLite?';get('chat-send').click();await wait(()=>document.querySelectorAll('.qa-reference').length===2);responses.length=0;arm=true;
      [...document.querySelectorAll('[data-qa-source]')].at(-1).click();await wait(()=>responses.some(item=>item.url.startsWith('/__knowledge_source__')&&item.data.code==='knowledge_changed'));
      assert(!get('kb-sources').querySelector('pre'),'detail-to-source mutation suppressed');get('kb-detail').close();return 'real source verified';
    })()'''.replace('ORIGINAL', json.dumps(original))
    try:
        assert 'real source verified' in run_chromium(tmp_path, f'http://127.0.0.1:{server.server_port}', expression)
    finally:
        server.shutdown();server.server_close()
