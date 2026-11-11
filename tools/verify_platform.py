import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import platform
from types import SimpleNamespace
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

if len(sys.argv) != 2:
    raise SystemExit('Usage: python tools/verify_platform.py /path/to/installed-package')
installed=Path(sys.argv[1]).resolve()
if not (installed/'selfos/__init__.py').is_file():
    raise SystemExit('Installed package directory not found')
for name in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):
    os.environ.pop(name,None)
sys.path.insert(0,str(installed))
original_cwd=Path.cwd()
with tempfile.TemporaryDirectory(prefix='selfos-wheel-smoke-') as tmp:
    root=Path(tmp);os.chdir(root);os.environ['SELFOS_ROOT']=str(root)
    env={**os.environ,'PYTHONPATH':str(installed),'PYTHONIOENCODING':'utf-8'}
    for name in ('serve','knowledge','harvest','auth'):
        run=subprocess.run([sys.executable,'-m','selfos',name,'--root',str(root),'--help'],
                           env=env,capture_output=True,text=True,encoding='utf-8')
        assert run.returncode==0,(name,run.stderr)
    from selfos.web import server
    from selfos.security.auth import AuthManager
    from selfos.storage.onboarding import ensure_vault_structure
    from selfos.web.rendering.auth import resources
    from selfos.sources.conversations import extract_conversations
    from selfos.sources.compaction import prepare_sessions
    from selfos.storage.pipeline import commit, restore_pipeline_backup
    assert str(server.__file__).startswith(str(installed))
    assert resources()['en']['login']=='Log in'
    auth=AuthManager(root,root/'vault',directory=root/'private-auth')
    auth.setup('a synthetic password for this test')
    if os.name != 'nt':
        assert auth.directory.stat().st_mode & 0o777 == 0o700
        assert auth.path.stat().st_mode & 0o777 == 0o600
    from selfos.paths import auth_directory
    if sys.platform == 'darwin':
        assert auth_directory()==Path.home()/'Library/Application Support/SelfOS'
    from selfos.storage.files import _pid_alive
    assert _pid_alive(os.getpid())

    ensure_vault_structure(root/'vault')
    assert 'Liam' not in (root/'vault/PROFILE.md').read_text(encoding='utf-8')
    (root/'dashboard.html').write_text('<html><body>SelfOS fixture</body></html>',encoding='utf-8')
    file=root/'fixture.jsonl'
    file.write_text(json.dumps({'type':'user','sessionId':'fixture','cwd':str(root/'example'),
                     'message':{'content':'I am building a reusable knowledge system with source evidence.'}})+'\n',encoding='utf-8')
    messages=extract_conversations([file]);parts=prepare_sessions(messages)
    assert len(messages)==1 and len(parts)==1
    run_id='20261111T120000-123456abcdef'
    state=root/'vault/.knowledge_pipeline.json'
    commit(root/'vault',{'.knowledge_pipeline.json':b'{}'},run_id,1)
    assert state.read_bytes()==b'{}'
    restore_pipeline_backup(root/'vault',run_id)
    assert not state.exists()
    http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);http.auth=auth
    threading.Thread(target=http.serve_forever,daemon=True).start()
    base='http://127.0.0.1:'+str(http.server_port)
    def request(path,body=None,cookie=''):
        headers={'Cookie':cookie}
        data=json.dumps(body).encode() if body is not None else None
        try: response=urlopen(Request(base+path,data=data,headers=headers),timeout=10)
        except HTTPError as error: response=error
        with response:
            raw=response.read()
            return SimpleNamespace(code=response.code,headers=response.headers,read=lambda:raw)
    try:
        assert request('/__knowledge__').code==401
        response=request('/auth/login',{'password':'a synthetic password for this test'})
        assert response.code==200
        cookie=response.headers['Set-Cookie'].split(';',1)[0]
        assert request('/',cookie=cookie).code==200
        assert request('/__knowledge_settings__',cookie=cookie).code==200
        assert request('/__model_settings__',cookie=cookie).code==200
        changed=request('/__model_settings__',{'provider':'openai','model':'fixture-model','base_url':'http://localhost:9999/v1','proxy_mode':'direct'},cookie)
        assert changed.code==200,changed.read()
        assert (root/'.selfos-model.json').exists()
        assert request('/auth/logout',{},cookie).code==200
        assert request('/__knowledge__',cookie=cookie).code==401
    finally:
        http.shutdown();http.server_close()
        os.chdir(original_cwd)
print('Installed wheel: four commands, locales, neutral templates, synthetic ingestion, backup/restore and authenticated HTTP passed; no model calls.')

print(json.dumps({'platform':platform.platform(),'machine':platform.machine(),'python':sys.version,'macOS':platform.mac_ver()[0],'installed':str(installed)},indent=2))
