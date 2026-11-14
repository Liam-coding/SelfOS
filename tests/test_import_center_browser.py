"""Actual Chromium exercises the center owner with synthetic loopback metadata."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from chromium_fixture import run_chromium


@pytest.mark.parametrize('locale', ['en', 'zh-CN'])
def test_center_source_handoff_stop_and_remount(tmp_path, locale):
    from selfos.web.rendering.resources import frontend_text
    from selfos.web.i18n import runtime
    page = '<html><head>' + runtime() + '</head><body>'
    page += '<script>' + frontend_text('scripts/ui-runtime.js') + '</script>'
    page += '''<script>
    window.calls=[];window.listeners=new Set();window.selfosUI.register('request',()=>({}));
    window.selfosUI.register('locale',()=>window.selfosI18n);
    window.selfosUI.register('jobs',()=>({snapshot:()=>({running:false}),
      subscribe:f=>{listeners.add(f);return()=>listeners.delete(f)},recover:()=>calls.push('recover'),stop:()=>{calls.push('stop');return Promise.resolve()}}));
    window.selfosUI.register('onboarding',()=>({open:()=>calls.push('sources'),preview:()=>calls.push('preview')}));
    window.selfosUploads={open:()=>calls.push('uploads')};window.openKnowledgeChanges=id=>calls.push('changes:'+id);
    </script>'''
    page += frontend_text('templates/import-center.html')
    page += '<script>selfosUI.init(document);</script></body></html>'
    data = {'sources': [{'kind': 'directory', 'path': '<img src=x onerror=window.hacked=true>',
             'available': True, 'excluded': False, 'scan': None, 'pending_parts': None}],
            'uploads': {'items': [], 'has_more': False, 'total': 0},
            'job': {'running': True, 'phase': 'running', 'completed': 1, 'total': 2},
            'model': {'provider': 'synthetic', 'model': 'fixture'}, 'diagnostics': [],
            'publication': {'operations': [{'id': 'fixture-op', 'status': 'completed',
                             'published': True, 'was_published': True, 'phase': 'publishing'}]}}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            raw = json.dumps(data).encode() if self.path.startswith('/__import_center__') else page.encode()
            self.send_response(200);self.send_header('Content-Type', 'application/json' if self.path.startswith('/__import_center__') else 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)));self.end_headers();self.wfile.write(raw)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    expression = r'''(async()=>{
      const assert=(v,m)=>{if(!v)throw Error(m)},wait=async f=>{for(let i=0;i<100;i++){if(f())return;await new Promise(r=>setTimeout(r,20))}throw Error('timeout')};
      selfosI18n.setLocale(LOCALE);
      assert(document.querySelector('#import-center-title').textContent===(LOCALE==='en'?'Import center':'导入中心'),'translated title');
      const owner=selfosUI.module('import-center');owner.open();await wait(()=>document.querySelector('#import-center-sources')?.textContent.includes('<img'));
      assert(!window.hacked&&!document.querySelector('#import-center-sources img'),'safe source label');
      assert(document.querySelector('#import-center-stop').disabled===false,'stop enabled');
      document.querySelector('#import-center-stop').click();await wait(()=>calls.includes('stop'));
      document.querySelector('#import-center-sources-edit').click();assert(calls.includes('sources'),'source handoff');
      assert(!document.querySelector('#import-center-dialog').open,'no modal stack');
      owner.open();await wait(()=>document.querySelector('#import-center-changes'));document.querySelector('#import-center-changes').click();
      assert(calls.includes('changes:fixture-op'),'committed changes');
      selfosUI.teardown(document);selfosUI.init(document);assert(listeners.size===1,'one subscription');
      selfosUI.module('import-center').open();await wait(()=>document.querySelector('#import-center-sources')?.textContent.includes('<img'));
      assert(!document.querySelector('#import-center-dialog').querySelector('img'),'safe remount');
      const originalFetch=window.fetch;let lateResolve;
      window.fetch=()=>new Promise(resolve=>lateResolve=resolve);
      owner.refresh();owner.close();window.fetch=originalFetch;owner.open();
      await wait(()=>document.querySelector('#import-center-sources')?.textContent.includes('<img'));
      lateResolve({ok:true,json:async()=>({sources:[{path:'stale response'}],job:{},uploads:{items:[]},publication:{operations:[]}})});
      await new Promise(resolve=>setTimeout(resolve,60));
      assert(!document.querySelector('#import-center-sources').textContent.includes('stale response'),'discard closed-request result');
      return 'center verified';
    })()'''.replace('LOCALE', json.dumps(locale))
    try:
        assert 'center verified' in run_chromium(tmp_path, f'http://127.0.0.1:{server.server_port}', expression, width=390)
    finally:
        server.shutdown();server.server_close()


def test_full_dashboard_center_uses_bounded_preview_and_commits_no_knowledge(tmp_path, monkeypatch):
    from selfos.web import server as runtime_server
    from selfos.sources.selection import save_sources
    from selfos.web.rendering.dashboard import generate_dashboard
    from selfos.web.rendering.refresh import refresh_dashboard
    app = tmp_path / 'app'
    vault = app / 'vault'
    vault.mkdir(parents=True)
    source = tmp_path / 'synthetic conversations'
    source.mkdir()
    save_sources(vault, {'roots': [str(source)], 'exclusions': []})
    dashboard = generate_dashboard(vault)
    html = dashboard.read_text(encoding='utf-8')
    for _ in range(3):
        html = refresh_dashboard(html)
        assert html.count('id="import-center-dialog"') == 1
        assert html.count('data-selfos-module="import-center"') == 1
    dashboard.write_text(html, encoding='utf-8')
    monkeypatch.setattr(runtime_server, 'ROOT', app)
    monkeypatch.setattr(runtime_server, 'VAULT', vault)
    monkeypatch.setattr(runtime_server, 'DASHBOARD', dashboard)
    server = ThreadingHTTPServer(('127.0.0.1', 0), runtime_server.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    expression = r'''(async()=>{
      const wait=async f=>{for(let i=0;i<150;i++){if(f())return;await new Promise(r=>setTimeout(r,30))}throw Error('timeout')};
      document.querySelector('#import-center-open').click();
      await wait(()=>document.querySelector('#import-center-sources').textContent.includes('synthetic conversations'));
      document.querySelector('#import-center-preview').click();
      await wait(()=>document.querySelector('#onboarding-dialog').open&&document.querySelector('#onboarding-preview-summary').textContent.includes('0'));
      const status=await(await fetch('/__import_center__')).json();
      if(!status.sources[0].scan||status.sources[0].scan.selected_parts!==0)throw Error('no empty preview receipt');
      if(status.publication.published_operation)throw Error('preview promoted to knowledge');
      selfosUI.module('onboarding').close();selfosUI.module('import-center').open();
      await wait(()=>document.querySelector('#import-center-preview').disabled===false);
      document.querySelector('#import-center-sources-edit').click();
      await wait(()=>document.querySelector('#onboarding-dialog').open);
      await wait(()=>document.querySelector('[data-onboarding-step="1"]').hidden===false);
      selfosUI.module('onboarding').close();selfosUI.module('import-center').open();
      const originalFetch=window.fetch;let release,previewRequests=0;
      window.fetch=(url,options={})=>{
        if(url==='/__onboarding__'&&!options.method)return new Promise(resolve=>release=()=>originalFetch(url,{}).then(resolve));
        if(url==='/__onboarding__'&&options.body?.includes('preview'))previewRequests++;
        return originalFetch(url,options);
      };
      document.querySelector('#import-center-preview').click();await wait(()=>!!release);
      selfosUI.module('onboarding').close();release();await new Promise(resolve=>setTimeout(resolve,250));
      window.fetch=originalFetch;if(previewRequests)throw Error('closed setup still started a scan');
      return 'bounded full dashboard verified';
    })()'''
    try:
        assert 'bounded full dashboard verified' in run_chromium(tmp_path, f'http://127.0.0.1:{server.server_port}', expression)
        assert not (vault / '.knowledge_pipeline.json').exists()
    finally:
        server.shutdown();server.server_close()
