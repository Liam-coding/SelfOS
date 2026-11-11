import json,threading,sys
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
import serve


def test_quiet_child_keeps_stream_alive_without_fake_progress(tmp_path,monkeypatch):
    original=serve.subprocess.Popen
    def launch(cmd,**kwargs):
        return original([sys.executable,'-u','-c',
            "import time;print('Organizing session 1/1 ...',flush=True);time.sleep(0.3);print('Saved session 1/1; backup test',flush=True)"],**kwargs)
    monkeypatch.setattr(serve.subprocess,'Popen',launch)
    monkeypatch.setattr(serve,'STREAM_HEARTBEAT',0.02,raising=False)
    monkeypatch.setattr(serve,'KNOWLEDGE_RUN',{'stop_file':None})
    server=ThreadingHTTPServer(('127.0.0.1',0),serve.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with urlopen(f'http://127.0.0.1:{server.server_port}/__knowledge_stream__',timeout=5) as response:
            line=response.readline().decode()
            while not line.startswith('data:'):line=response.readline().decode()
            assert 'Organizing session' in line
            assert response.readline()==b'\n'
            assert response.readline().startswith(b':'),'Quiet generation needs SSE heartbeat comments'
            rest=response.read().decode()
        assert '"done": true' in rest and '"ok": true' in rest
        assert serve.KNOWLEDGE_RUN['stop_file'] is None
    finally:server.shutdown();server.server_close()
