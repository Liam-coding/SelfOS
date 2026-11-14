"""Native Chromium loopback fixture; no browser package or real backend."""
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen
import pytest

CDP_HARNESS = r"""
const fs=require('fs');
(async()=>{
 const info=await(await fetch(process.argv[2]+'/json/version')).json(),ws=new WebSocket(info.webSocketDebuggerUrl);
 await new Promise(r=>ws.onopen=r);let seq=0,loadResolve;const pending=new Map();
 ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.method==='Page.loadEventFired'&&loadResolve)loadResolve();if(m.id){const [r,j]=pending.get(m.id);pending.delete(m.id);m.error?j(Error(JSON.stringify(m.error))):r(m.result);}};
 const call=(method,params={},sessionId)=>new Promise((r,j)=>{const id=++seq;pending.set(id,[r,j]);ws.send(JSON.stringify({id,method,params,sessionId}));});
 const {targetId}=await call('Target.createTarget',{url:'about:blank'});
 const {sessionId}=await call('Target.attachToTarget',{targetId,flatten:true});
 await call('Emulation.setDeviceMetricsOverride',{width:Number(process.argv[5]||390),height:844,deviceScaleFactor:1,mobile:true},sessionId);
 await call('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]},sessionId);
 await call('Page.enable',{},sessionId);const loaded=new Promise(resolve=>loadResolve=resolve);
 await call('Page.navigate',{url:process.argv[3]},sessionId);
 await loaded;await call('Runtime.enable',{},sessionId);
 const out=await call('Runtime.evaluate',{expression:fs.readFileSync(process.argv[4],'utf8'),awaitPromise:true,returnByValue:true},sessionId);
 if(out.exceptionDetails)throw Error(JSON.stringify(out.exceptionDetails));console.log(out.result.value);
 const screenshot=await call('Page.captureScreenshot',{format:'png'},sessionId);fs.writeFileSync(process.argv[4]+'.png',Buffer.from(screenshot.data,'base64'));
 await call('Browser.close');ws.close();process.exit(0);
})().catch(e=>{console.error(e);process.exit(1);});
setTimeout(()=>{console.error('CDP timeout');process.exit(2)},30000);
"""

def run_chromium(tmp_path, url, expression, width=390):
    chrome=Path(os.environ.get('SELFOS_CHROME','C:/Program Files/Google/Chrome/Application/chrome.exe'))
    node=shutil.which('node')
    if not node or not chrome.exists():pytest.skip('Node and SELFOS_CHROME are needed')
    script=tmp_path/'browser.cjs';script.write_text(CDP_HARNESS,encoding='utf-8')
    check=tmp_path/'checks.js';check.write_text(expression,encoding='utf-8')
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    endpoint=f'http://127.0.0.1:{port}'
    process=subprocess.Popen([str(chrome),'--headless=new','--no-sandbox','--disable-gpu','--no-proxy-server',f'--remote-debugging-port={port}',f'--user-data-dir={tmp_path / "chrome"}'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    try:
        for attempt in range(100):
            try:
                with urlopen(endpoint+'/json/version',timeout=1):break
            except OSError:time.sleep(.1)
        else:raise AssertionError('Synthetic browser failed to start')
        result=subprocess.run([node,str(script),endpoint,url,str(check),str(width)],capture_output=True,text=True,timeout=40)
        assert result.returncode==0,result.stdout+result.stderr
        return result.stdout
    finally:
        if process.poll() is None:process.kill()
