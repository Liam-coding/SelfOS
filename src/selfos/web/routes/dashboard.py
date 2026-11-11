"""Dashboard HTTP routes; no server imports."""
import json
import tempfile
import uuid
import re
from pathlib import Path

class DashboardRoutes:
    def do_GET(self):
        if not self._local_request():return self._send_json(403,{'error':'Use the local SelfOS dashboard'})
        if not self._auth_guard():return
        from urllib.parse import urlparse,parse_qs
        parsed_path=urlparse(self.path)
        if parsed_path.path == '/__knowledge_run__':
            origin=self.headers.get('Origin');host=self.headers.get('Host','')
            if (origin and origin!=f'http://{host}') or self.headers.get('Sec-Fetch-Site')=='cross-site':
                return self._send_json(403,{'error':'Use the local SelfOS dashboard'})
            return self._send_json(200, self.runtime.knowledge_run_status())
        if parsed_path.path in ('/__knowledge__','/__knowledge_item__','/__knowledge_source__','/__knowledge_timeline__'):
            origin=self.headers.get('Origin');host=self.headers.get('Host','')
            if (origin and origin!=f'http://{host}') or self.headers.get('Sec-Fetch-Site')=='cross-site':
                return self._send_json(403,{'error':'Knowledge is available from the local dashboard only'})
            from selfos.app.library import list_knowledge, knowledge_detail, knowledge_source, knowledge_timeline
            qs=parse_qs(parsed_path.query)
            try:
                if parsed_path.path=='/__knowledge_timeline__':
                    result=knowledge_timeline(self.runtime.VAULT,qs.get('id',[''])[0],
                        category=qs.get('category',['all'])[0],offset=int(qs.get('offset',['0'])[0]),
                        limit=int(qs.get('limit',['50'])[0]),revision=qs.get('revision',[''])[0])
                elif parsed_path.path=='/__knowledge__':
                    result=list_knowledge(self.runtime.VAULT,category=qs.get('category',['all'])[0],query=qs.get('query',[''])[0],
                        offset=int(qs.get('offset',['0'])[0]),limit=int(qs.get('limit',['50'])[0]))
                elif parsed_path.path=='/__knowledge_item__':
                    result=knowledge_detail(self.runtime.VAULT,qs.get('id',[''])[0],
                        source_offset=int(qs.get('source_offset',['0'])[0]))
                else:result=knowledge_source(self.runtime.VAULT,qs.get('id',[''])[0])
                return self._send_json(200,result)
            except KeyError as error:return self._send_json(404,{'error':str(error).strip("'")})
            except (ValueError,TypeError) as error:return self._send_json(400,{'error':str(error)})
        if self.path == '/__knowledge_settings__':
            from selfos.app.knowledge import get_status
            return self._send_json(200, get_status(self.runtime.VAULT))
        if self.path == '/__model_settings__':
            from selfos.providers.settings import public_config
            return self._send_json(200, public_config(self.runtime.ROOT))
        if self.path in ("/", "/dashboard.html"):
            if self.runtime.DASHBOARD.exists():
                body = self.runtime.DASHBOARD.read_bytes()
                from selfos.web.rendering.overall import STYLE, integrate_overall
                page=body.decode('utf-8')
                from selfos.web.rendering.knowledge import refresh_controls
                page=refresh_controls(page)
                from selfos.web.rendering.library import refresh_library
                page=refresh_library(page)
                page=re.sub(r'<style id="selfos-visual-system">.*?</style>',lambda _:STYLE,page,count=1,flags=re.S)
                body=integrate_overall(page).encode('utf-8')
                from selfos.web.rendering.auth import ACCOUNT_CONTROLS
                body=body.replace(b'</body>',ACCOUNT_CONTROLS.encode('utf-8')+b'</body>')
                body=body.replace(b"let lang = localStorage.getItem('selfos-lang') === 'en' ? 'en' : 'zh';",
                                  b"let lang = localStorage.getItem('selfos-lang') === 'zh' ? 'zh' : 'en';")
                from selfos.web.rendering.model import CONTROLS
                if b'id="model-settings-entry"' not in body:
                    body=body.replace(b'</body>',CONTROLS.encode('utf-8')+b'</body>')
                self._send(200, body, "text/html; charset=utf-8")
            else:
                self._send_json(404, {"error": "dashboard.html not found — run python -m selfos harvest first"})
        elif self.path == "/__staging__":
            staging_dir = self.runtime.VAULT / "91_Staging"
            files = []
            if staging_dir.exists():
                for f in sorted(staging_dir.glob("*.md")):
                    text = f.read_text(encoding="utf-8", errors="replace")
                    # parse frontmatter target
                    target = ""
                    for line in text.splitlines():
                        if line.startswith("target:"):
                            target = line.split(":", 1)[1].strip()
                            break
                    files.append({
                        "name": f.name,
                        "target": target,
                        "content": text,
                    })
            self._send_json(200, {"files": files})
        elif self.path.startswith(("/__harvest_stream__", "/__knowledge_stream__")):
            # SSE endpoint: stream harvest.py stdout line by line
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(self.path)
            knowledge = parsed.path == "/__knowledge_stream__"
            if parsed.path not in ("/__knowledge_stream__", "/__harvest_stream__"):
                return self._send_json(404, {"error": "not found"})
            if knowledge:
                origin = self.headers.get("Origin")
                host = self.headers.get("Host", "")
                if (origin and origin != f"http://{host}") or self.headers.get("Sec-Fetch-Site") == "cross-site":
                    return self._send_json(403, {"error": "Knowledge import must be started from the local SelfOS dashboard"})
            qs = parse_qs(parsed.query)
            full = qs.get("full", ["0"])[0] == "1"
            from selfos.app.jobs import command, child_environment
            cmd = command('knowledge' if knowledge else 'harvest', self.runtime.ROOT)
            if knowledge:
                cmd.extend(['--vault', str(self.runtime.VAULT)])
            if full and not knowledge:
                cmd.append("--full")
            stop_file = None
            if knowledge:
                if qs.get('action', [''])[0] == 'rebuild':
                    cmd.append('--rebuild')
                with self.runtime.KNOWLEDGE_RUN_LOCK:
                    if self.runtime.KNOWLEDGE_RUN["stop_file"] is not None:
                        return self._send_json(409, {"error": "Knowledge import already running"})
                    stop_file = Path(tempfile.gettempdir()) / ("selfos-stop-" + uuid.uuid4().hex)
                    self.runtime.KNOWLEDGE_RUN.clear()
                    self.runtime.KNOWLEDGE_RUN.update(stop_file=stop_file, process=None, job_id=uuid.uuid4().hex,
                                         phase='starting', saved=set(), total=0, last_line='', result=None)
                cmd.extend(["--stop-file", str(stop_file)])
            proc = None
            outcome = None
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                proc = self.runtime.subprocess.Popen(
                    cmd, stdout=self.runtime.subprocess.PIPE, stderr=self.runtime.subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", cwd=str(self.runtime.ROOT),
                    bufsize=1, env=child_environment()
                )
                if knowledge:
                    with self.runtime.KNOWLEDGE_RUN_LOCK: self.runtime.KNOWLEDGE_RUN['process'] = proc
                for line in self.runtime._process_lines(proc, self.runtime._knowledge_run_line if knowledge else None):
                    if not self._session_alive():raise ConnectionAbortedError('Login session expired. Sign in again to resume.')
                    if line is None:
                        self.wfile.write(b': heartbeat\n\n')
                        self.wfile.flush()
                    else:
                        data = json.dumps({"line": line.rstrip("\n")})
                        self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                        self.wfile.flush()
                ok = proc.returncode == 0
                outcome = {'done': True, 'ok': ok, 'cancelled': bool(stop_file and stop_file.exists())}
                self.wfile.write(f"data: {json.dumps(outcome)}\n\n".encode("utf-8"))
                self.wfile.flush()
            except Exception as e:
                try:
                    self.wfile.write(f"data: {json.dumps({'done': True, 'ok': False, 'error': str(e)})}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    pass
            finally:
                if stop_file is not None:
                    cancelled = stop_file.exists()
                    if proc is not None and proc.poll() is None:
                        # Let the child finish its current request and atomic save.
                        stop_file.touch()
                        cancelled = True
                        proc.wait()
                    reader = getattr(proc, '_selfos_output_reader', None)
                    if reader is not None: reader.join()
                    if outcome is None:
                        outcome = {'done': True, 'ok': bool(proc is not None and proc.returncode == 0),
                                   'cancelled': cancelled}
                    with self.runtime.KNOWLEDGE_RUN_LOCK:
                        self.runtime.KNOWLEDGE_RUN["stop_file"] = None
                        self.runtime.KNOWLEDGE_RUN['process'] = None
                        self.runtime.KNOWLEDGE_RUN['result'] = outcome
                        self.runtime.KNOWLEDGE_RUN['phase'] = ('stopped' if outcome['cancelled'] else
                                                  'completed' if outcome['ok'] else 'failed')
                    stop_file.unlink(missing_ok=True)
        else:
            self._send_json(404, {"error": "not found"})
