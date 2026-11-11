"""Exercise real CLI/HTTP stop and resume using temporary conversations and fake AI."""
import json,threading,time,sys
from http.server import ThreadingHTTPServer
from urllib.request import Request,urlopen
import serve
import socket
import io
from tests.test_knowledge_service import source


def test_header_disconnect_releases_reserved_run(monkeypatch):
    monkeypatch.setattr(serve,'KNOWLEDGE_RUN',{'stop_file':None})
    handler=serve.Handler.__new__(serve.Handler)
    handler.path='/__knowledge_stream__'
    from types import SimpleNamespace
    handler.headers={'Host':'127.0.0.1:7070'}
    handler.server=SimpleNamespace(server_port=7070)
    handler.client_address=('127.0.0.1',12345)
    handler.wfile=io.BytesIO()
    handler.send_response=lambda *args:None
    handler.send_header=lambda *args:None
    def disconnect():raise BrokenPipeError('Client closed before stream headers')
    handler.end_headers=disconnect
    handler.do_GET()
    state=serve.knowledge_run_status()
    assert not state['running'] and state['phase']=='failed'
    assert state['result']['ok'] is False


def test_disconnected_stream_stops_child_and_tracks_final_save(tmp_path, monkeypatch):
    original = serve.subprocess.Popen
    ready = tmp_path/'ready'
    script = r'''
import sys,time
from pathlib import Path
marker,ready=sys.argv[1:]
print('Knowledge: 2 compact session parts, 2 pending; workers 1',flush=True)
print('Saved session 1/2',flush=True)
Path(ready).touch()
while not Path(marker).exists():time.sleep(0.01)
print('Saved session 2/2',flush=True)
'''
    def launch(cmd, **kwargs):
        return original([sys.executable,'-u','-c',script,cmd[-1],str(ready)],**kwargs)
    monkeypatch.setattr(serve.subprocess,'Popen',launch)
    monkeypatch.setattr(serve,'KNOWLEDGE_RUN',{'stop_file':None})
    monkeypatch.setattr(serve,'STREAM_HEARTBEAT',0.03)
    server=ThreadingHTTPServer(('127.0.0.1',0),serve.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        response=urlopen(base+'/__knowledge_stream__',timeout=10)
        deadline=time.monotonic()+5
        while not ready.exists() and time.monotonic()<deadline:time.sleep(0.01)
        assert ready.exists()
        response.fp.raw._sock.shutdown(socket.SHUT_RDWR)
        response.close()
        deadline=time.monotonic()+5
        while serve.knowledge_run_status()['running'] and time.monotonic()<deadline:time.sleep(0.01)
        state=serve.knowledge_run_status()
        assert not state['running'] and state['phase']=='stopped'
        assert state['completed']==2 and state['result']['cancelled']
        assert 'process' not in state and 'stop_file' not in state
    finally:
        marker=serve.KNOWLEDGE_RUN.get('stop_file')
        if marker is not None:marker.touch()
        server.shutdown();server.server_close()


def test_http_stop_preserves_checkpoint_and_resume_reuses_it(tmp_path,monkeypatch):
    roots,path=source(tmp_path);rows=[json.loads(line) for line in path.read_text().splitlines()]
    rows[0]['payload'].update(id='second',cwd='C:/projects/beta')
    rows[1]['payload']['content'][0]['text']+=' Second project.'
    (roots/'second.jsonl').write_text('\n'.join(json.dumps(row) for row in rows))
    originals={p.name:p.read_bytes() for p in roots.iterdir()}
    vault=tmp_path/'vault';ready=tmp_path/'ready';calls=tmp_path/'calls';launches=[]
    original=serve.subprocess.Popen
    script=r'''
import sys,time
from pathlib import Path
import knowledge
from tests.test_knowledge_service import summarize,refine
vault,roots,ready,calls,mode,stop=sys.argv[1:]
knowledge.local_roots=lambda:[Path(roots)]
def generate(item):
    with Path(calls).open('a') as stream:stream.write(item['session_id']+'\n')
    Path(ready).touch()
    if mode=='pause':
        while not Path(stop).exists():time.sleep(0.01)
    return summarize(item)
knowledge.api_summarizer=lambda *args,**kwargs:generate
knowledge.api_refiner=lambda *args,**kwargs:refine
sys.argv=['knowledge.py','--vault',vault,'--workers','1','--stop-file',stop]
knowledge.main()
'''
    def launch(cmd,**kwargs):
        mode='pause' if not launches else 'resume';launches.append(mode)
        return original([sys.executable,'-u','-c',script,str(vault),str(roots),str(ready),str(calls),mode,cmd[-1]],**kwargs)
    monkeypatch.setattr(serve.subprocess,'Popen',launch)
    monkeypatch.setattr(serve,'VAULT',vault)
    monkeypatch.setattr(serve,'KNOWLEDGE_RUN',{'stop_file':None})
    server=ThreadingHTTPServer(('127.0.0.1',0),serve.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        with urlopen(base+'/__knowledge_run__') as status:
            assert json.load(status)['running'] is False
        with urlopen(base+'/__knowledge_stream__',timeout=15) as response:
            deadline=time.monotonic()+10
            while not ready.exists() and time.monotonic()<deadline:time.sleep(0.01)
            assert ready.exists(),'Synthetic child did not reach first request'
            with urlopen(base+'/__knowledge_run__') as status:
                active=json.load(status)
                assert active['running'] and active['phase']=='running'
                assert active['job_id'] and active['total']==2
            with urlopen(Request(base+'/__knowledge_stop__',data=b'{}',method='POST'),timeout=5) as stop_response:
                assert json.load(stop_response)['running'] is True
            stream=response.read().decode()
        assert '"cancelled": true' in stream
        with urlopen(base+'/__knowledge_run__') as status:
            stopped=json.load(status)
            assert not stopped['running'] and stopped['phase']=='stopped'
            assert stopped['completed']==1 and stopped['result']['cancelled']
        assert not (vault/'.knowledge_pipeline.json').exists()
        with urlopen(base+'/__knowledge_settings__') as status:
            assert json.load(status)['saved_checkpoints']==1
        assert calls.read_text().splitlines()==['original']
        with urlopen(base+'/__knowledge_stream__',timeout=15) as response:
            assert '"ok": true' in response.read().decode()
        assert calls.read_text().splitlines()==['original','second']
        state=json.loads((vault/'.knowledge_pipeline.json').read_text())
        assert len(state['cards'])==2 and len(state['summaries'])==2
        assert {p.name:p.read_bytes() for p in roots.iterdir()}==originals
        assert serve.KNOWLEDGE_RUN['stop_file'] is None
        with urlopen(base+'/__knowledge_run__') as status:
            completed=json.load(status)
            assert not completed['running'] and completed['phase']=='completed'
            assert completed['result']['ok'] and completed['job_id']!=active['job_id']
    finally:
        if serve.KNOWLEDGE_RUN['stop_file'] is not None:serve.KNOWLEDGE_RUN['stop_file'].touch()
        server.shutdown();server.server_close()
