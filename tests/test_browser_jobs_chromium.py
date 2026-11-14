"""Real EventSource connections use an entirely synthetic loopback server."""
import json
import queue
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from chromium_fixture import run_chromium
from selfos.web.i18n import runtime
from selfos.web.rendering.resources import frontend_text


def test_native_jobs_disconnect_stop_recovery_and_completion_owners(tmp_path):
    from selfos.web.rendering.knowledge import CONTROLS
    from selfos.web.rendering.onboarding import CONTROLS as onboarding
    from selfos.web.rendering.overall import OVERVIEW

    counts=Counter();streams=[];lock=threading.Lock()
    run={'running':False}
    usage={'budget':{'max_requests':100},'runs':[]}
    settings={'settings':{'domains':['work'],'detail':'balanced'},'counts':{},'saved_checkpoints':0,'publication':{'operations':[]},'usage':usage}
    guide={'progress':{'step':1,'status':'active'},'availability':[],'sources':{'roots':['/synthetic'],'exclusions':[]},'model':{'provider':'openai','model':'fixture'},'preview':None,'budget':None,'knowledge':{'counts':{},'saved_checkpoints':0}}
    scripts=''.join('<script>'+frontend_text('scripts/'+name)+ '</script>' for name in ['dashboard-imports.js','dashboard-staging.js'])
    roots='<div id="harvest-modal"></div><div id="progress-modal"><div id="progress-bar"></div><pre id="progress-log"></pre><span id="progress-icon"></span><span id="progress-title"></span><button id="progress-done-btn"></button><button id="knowledge-stop-btn"></button></div><button id="staging-btn"></button><div id="staging-modal"><div id="staging-file-list"></div><button id="staging-apply-btn"></button></div>'
    instrumentation=r"""<script>window.errors=[];addEventListener('error',event=>errors.push(event.message));window.intervals=new Set();window.intervalStarts=0;const nativeInterval=setInterval,nativeClearInterval=clearInterval;window.setInterval=(...args)=>{intervalStarts++;const id=nativeInterval(...args);intervals.add(id);return id;};window.clearInterval=id=>{intervals.delete(id);nativeClearInterval(id);};</script>"""
    html=('<!doctype html><html><head>'+runtime()+'<script>'+frontend_text('scripts/ui-runtime.js')+frontend_text('scripts/ui-request.js')+"selfosUI.register('settings',()=>({openModel(){},onModelClosed(){return()=>{};}}));selfosUI.register('knowledge',()=>({openDetail(){},browse(){}}));"+'</script>'+instrumentation+'</head><body>'+roots+OVERVIEW+CONTROLS+onboarding+scripts+'<script>'+frontend_text('scripts/ui-bootstrap.js')+'</script></body></html>').encode()

    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args):pass
        def respond(self,data,content_type='application/json'):
            payload=data if isinstance(data,bytes) else json.dumps(data).encode()
            self.send_response(200);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        def do_GET(self):
            path=urlsplit(self.path).path
            with lock:counts[path]+=1
            if path.endswith('_stream__'):
                channel=queue.Queue()
                with lock:streams.append(channel)
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Cache-Control','no-cache');self.end_headers()
                try:
                    self.wfile.write(b'data: {"line":"synthetic connection opened"}\n\n');self.wfile.flush()
                    while True:
                        try:message=channel.get(timeout=5)
                        except queue.Empty:message='heartbeat'
                        if message is None:break
                        payload=b': heartbeat\n\n' if message=='heartbeat' else ('data: '+json.dumps(message)+'\n\n').encode()
                        self.wfile.write(payload);self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
                finally:self.close_connection=True
                return
            data={'/__knowledge_run__':run,'/__knowledge_usage__':usage,'/__knowledge_settings__':settings,'/__knowledge_quality__':{'counts':{},'categories':{},'stages':{},'examples':[],'jobs':[]},'/__staging__':{'files':[]},'/__onboarding__':guide}.get(path)
            if path=='/fixture-stats':return self.respond({'counts':dict(counts),'streams':len(streams)})
            if data is not None:return self.respond(data)
            if path=='/':return self.respond(html,'text/html; charset=utf-8')
            self.send_error(404)
        def do_POST(self):
            path=urlsplit(self.path).path
            length=int(self.headers.get('Content-Length','0'));body=json.loads(self.rfile.read(length) or b'{}')
            with lock:counts['POST '+path]+=1
            if path=='/fixture-control':
                if 'run' in body:run.clear();run.update(body['run'])
                if 'stream' in body:streams[body['stream']].put(body.get('message'))
                return self.respond({})
            if path=='/__knowledge_stop__':return self.respond({})
            self.send_error(404)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    checks=r"""(async()=>{
 const jobs=selfosUI.module('jobs'),assert=(value,message)=>{if(!value)throw Error(message);};
 const wait=async predicate=>{const until=Date.now()+6000;while(!predicate()){if(Date.now()>until)throw Error('state timeout '+JSON.stringify(jobs.snapshot()));await new Promise(resolve=>setTimeout(resolve,20));}};
 const stats=async()=>await(await fetch('/fixture-stats')).json(),control=async body=>await fetch('/fixture-control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 await wait(()=>jobs.snapshot().phase==='idle');await selfosUI.module('import-settings').open();
 const custom=document.getElementById('knowledge-custom');custom.value='dirty-native-draft';custom.dispatchEvent(new Event('input',{bubbles:true}));
 const guide=document.getElementById('onboarding-roots');guide.value='dirty-native-sources';guide.dispatchEvent(new Event('input',{bubbles:true}));
 const before=await stats();
 for(const owner of ['jobs','import-settings','usage','publication','quality','overview','staging','onboarding']){const script=[...document.scripts].find(node=>node.textContent.includes("register('"+owner+"'"));const repeat=document.createElement('script');repeat.textContent=script.textContent;document.body.append(repeat);}
 selfosUI.init(document);selfosUI.init(document);selfosUI.init(document);
 const repeated=await stats();for(const [path,count]of Object.entries(before.counts))if(path.startsWith('/__'))assert(repeated.counts[path]===count,'duplicate initial read '+path);
 assert(custom.value==='dirty-native-draft'&&guide.value==='dirty-native-sources','draft reset');
 let finished=0;document.addEventListener('selfos-import-finished',()=>finished++);
 jobs.start(false,true);jobs.start(true,false);await wait(()=>intervals.size===1);
 await new Promise(resolve=>setTimeout(resolve,100));assert((await stats()).streams===1,'duplicate stream');selfosUI.init(document);assert(intervalStarts===1,'duplicate usage interval');
 await Promise.all([jobs.stop(),jobs.stop()]);assert((await stats()).counts['POST /__knowledge_stop__']===1,'duplicate stop POST');
 await control({stream:0,message:{done:true,ok:true,cancelled:true}});await wait(()=>jobs.snapshot().phase==='cancelled');assert(finished===1&&intervals.size===0,'cancel terminal/interval');
 await new Promise(resolve=>setTimeout(resolve,100));assert(custom.value==='dirty-native-draft'&&guide.value==='dirty-native-sources','completion replaced dirty form');
 const beforeHarvest=(await stats()).counts['/__knowledge_run__'];jobs.start(false,false);await new Promise(resolve=>setTimeout(resolve,100));await control({stream:1});await wait(()=>jobs.snapshot().phase==='failed');
 assert((await stats()).counts['/__knowledge_run__']===beforeHarvest&&finished===1,'Harvest used knowledge recovery');
 await control({run:{running:true,total:4,completed:1,phase:'running'}});jobs.start(false,true);await new Promise(resolve=>setTimeout(resolve,100));await control({stream:2});await wait(()=>jobs.snapshot().phase==='recovering');
 assert(intervals.size===1&&intervalStarts===2,'recovery duplicated usage timer');const streamsBefore=(await stats()).streams;
 selfosUI.teardown();assert(intervals.size===0,'teardown leaked interval');assert((await stats()).counts['POST /__knowledge_stop__']===1,'teardown stopped server');
 selfosUI.init(document);await wait(()=>jobs.snapshot().phase==='recovering');assert((await stats()).streams===streamsBefore,'remount restarted stream');
 await control({run:{running:false,result:{ok:true}}});await wait(()=>jobs.snapshot().phase==='succeeded');assert(finished===2&&intervals.size===0,'recovery terminal/interval');
 assert(!errors.length,errors.join(';'));selfosUI.teardown();return 'native SSE lifecycle passed';
 })()"""
    try:
        run_chromium(tmp_path,f'http://127.0.0.1:{server.server_port}/',checks)
        assert counts['POST /__knowledge_stop__']==1
        assert not any(path in counts for path in ['/chat','/__model_test__'])
    finally:
        for channel in streams:channel.put(None)
        server.shutdown();server.server_close()
