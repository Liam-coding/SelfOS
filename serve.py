"""
serve.py — SelfOS local server
  python serve.py          # default port 7070
  python serve.py --port 8080

Endpoints:
  GET  /              → dashboard.html
  POST /__harvest__   → runs harvest.py, returns JSON
  POST /chat          → proxies to Claude API with vault context
"""

import json
import os
import subprocess
import sys
import threading
import tempfile
import uuid
import queue
import re
import ipaddress
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent
VAULT = ROOT / "vault"
DASHBOARD = ROOT / "dashboard.html"
KNOWLEDGE_RUN = {"stop_file": None}
KNOWLEDGE_RUN_LOCK = threading.Lock()
STREAM_HEARTBEAT = 10


def knowledge_run_status():
    """Return only public, ephemeral task metadata; never expose process or paths."""
    with KNOWLEDGE_RUN_LOCK:
        run = KNOWLEDGE_RUN
        marker = run.get('stop_file')
        proc = run.get('process')
        running = marker is not None
        phase = run.get('phase', 'idle')
        if running:
            phase = ('stopping' if marker.exists() else
                     'starting' if proc is None else
                     'finishing' if proc.poll() is not None else 'running')
        return dict(running=running, phase=phase, job_id=run.get('job_id'),
                    completed=len(run.get('saved', set())), total=run.get('total', 0),
                    last_line=run.get('last_line', ''), result=run.get('result'))


def _knowledge_run_line(line):
    with KNOWLEDGE_RUN_LOCK:
        KNOWLEDGE_RUN['last_line'] = line[:2000]
        total = re.search(r'Knowledge: \d+ compact session parts, (\d+) pending', line)
        if total: KNOWLEDGE_RUN['total'] = int(total.group(1))
        saved = re.search(r'Saved (?:session|batch) (\d+)/(\d+)', line)
        if saved:
            KNOWLEDGE_RUN.setdefault('saved', set()).add(int(saved.group(1)))
            KNOWLEDGE_RUN['total'] = int(saved.group(2))


def _process_lines(proc, on_line=None):
    """Drain stdout independently so a quiet child never blocks SSE heartbeats."""
    output=queue.Queue()
    def read():
        try:
            while True:
                line=proc.stdout.readline()
                if line=='':break
                if on_line is not None: on_line(line.rstrip('\n'))
                output.put(('line',line))
            output.put(('done',None))
        except Exception as error:output.put(('error',error))
    reader = threading.Thread(target=read,daemon=True)
    proc._selfos_output_reader = reader
    reader.start()
    while True:
        try:kind,value=output.get(timeout=STREAM_HEARTBEAT)
        except queue.Empty:
            yield None
            continue
        if kind=='error':raise value
        if kind=='done':
            if proc.poll() is None:proc.wait()
            return
        yield value

# ── Vault context ──────────────────────────────────────────────────────────────

_CONTEXT_FILES = [
    "PROFILE.md",
    "NOW.md",
    "GOALS.md",
    "DECISIONS.md",
]

def _load_vault_context() -> str:
    parts = []

    # Current scores — most important context for the chat
    scores_file = VAULT / "SCORES.md"
    if scores_file.exists():
        text = scores_file.read_text(encoding="utf-8").strip()
        if text:
            parts.append(f"## Current Scores\n{text}")

    for name in _CONTEXT_FILES:
        p = VAULT / name
        if p.exists():
            text = p.read_text(encoding="utf-8").strip()
            if text:
                parts.append(f"## {name}\n{text}")

    # Latest digest
    inbox = VAULT / "90_Inbox"
    if inbox.exists():
        digests = sorted(inbox.glob("*-sessions-digest.md"), reverse=True)
        if digests:
            text = digests[0].read_text(encoding="utf-8").strip()
            if text:
                parts.append(f"## Latest Session Digest ({digests[0].name})\n{text[:4000]}")

    state_path = VAULT / ".knowledge_pipeline.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        for category in ('personal_facts', 'preferences'):
            records = [{k: r.get(k) for k in ('text', 'domain', 'conflict', 'observed_at')}
                       for r in state.get(category, [])]
            if records:
                parts.append('## ' + category + '\n' + json.dumps(records, ensure_ascii=False))
        cards = sorted(state.get("cards", {}).values(), key=lambda c: c.get("updated_at", ""), reverse=True)
        for card in cards[:20]:
            current = {k: card.get(k) for k in ("title", "intent", "status", "updated_at", "verified")}
            for field in ("blockers", "next_steps", "decisions"):
                limit = 2000 if field == "next_steps" else 400
                current[field] = [str(v)[:limit] for v in card.get(field, [])[-8:]]
            parts.append("## Current project state\n" + json.dumps(current, ensure_ascii=False))
    else:
        cards = sorted((VAULT / "02_Work/projects").glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        for card in cards[:20]:
            parts.append("## Project summary\n" + card.read_text(encoding="utf-8")[:4000])
    lessons = VAULT / "05_Life/lessons.md"
    if lessons.exists():
        parts.append("## Reusable lessons\n" + lessons.read_text(encoding="utf-8")[-8000:])
    return "\n\n---\n\n".join(parts)


SYSTEM_PROMPT = """You are a warm, personal AI companion embedded in SelfOS. You know the user well from their vault — their life, work, research, and goals.

Start every conversation like a friend catching up: ask how they're feeling, mention something general about life or energy levels, or just be present. Don't lead with scores or work analysis unless they bring it up first.

When the user wants to go deeper on scores or a specific dimension, you can explain what the scores mean, identify what needs attention, and give concrete suggestions. But always follow their lead — start human, not analytical.

STRICT OUTPUT RULES — no exceptions:
- Plain text only. Zero markdown. No asterisks, no bold, no italics, no hyphens as bullets, no headers, no backticks.
- Short and direct. Two to four sentences normally.
- Conversational, like a friend who knows you well.
- Only reference what is actually in the vault data. If a field is empty, say so briefly and move on.
- Match the user's language (Chinese or English).

Vault context:
{context}"""

# ── API call ───────────────────────────────────────────────────────────────────

def _get_config() -> tuple[str, str]:
    """Return (api_key, base_url) from env or .env file."""
    from harvest import _get_api_config
    return _get_api_config(ROOT)


def _call_claude(messages: list[dict], api_key: str, base_url: str) -> str:
    context = _load_vault_context()
    system = SYSTEM_PROMPT.format(context=context)

    payload = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 1024,
        "system": system,
        "messages": messages,
    }).encode()

    req = Request(
        f"{base_url}/v1/messages",
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with __import__('model_client').request_opener(ROOT)(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["content"][0]["text"]


# ── HTTP handler ───────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def _auth(self):
        if not hasattr(self.server,'auth'):
            from selfos_auth import AuthManager
            self.server.auth=AuthManager(ROOT,VAULT)
        return self.server.auth

    def _token(self):
        from http.cookies import SimpleCookie,CookieError
        try:
            cookies=SimpleCookie(self.headers.get('Cookie',''))
            return cookies['selfos_session'].value if 'selfos_session' in cookies else ''
        except CookieError:return ''

    def _session_alive(self):
        return self._auth().authenticated(self._token())

    def _auth_guard(self):
        from urllib.parse import urlsplit
        path=urlsplit(self.path).path;auth=self._auth();token=self._token()
        if self.command=='GET' and path=='/auth/status':
            self._send_json(200,{'state':auth.status(),'authenticated':auth.authenticated(token)})
            return False
        if self.command=='POST' and path in ('/auth/setup','/auth/login','/auth/logout','/auth/change'):
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=8192:raise ValueError('Invalid authentication request.')
                body=json.loads(self._read_body())
                if not isinstance(body,dict):raise ValueError('Invalid authentication request.')
                new_token=''
                if path=='/auth/setup':
                    auth.setup(body.get('password'));new_token=auth.login(body.get('password'))
                elif path=='/auth/login':new_token=auth.login(body.get('password'))
                else:
                    if not auth.authenticated(token):
                        self._send_json(401,{'error':'Please log in again.','error_code':'login_required'});return False
                    if path=='/auth/logout':auth.logout(token)
                    else:auth.change(token,body.get('current_password'),body.get('password'))
                cookie='selfos_session='+new_token+'; Path=/; HttpOnly; SameSite=Strict; Max-Age='+str(auth.TTL if new_token else 0)
                self._send(200,json.dumps({'ok':True}).encode(),extra_headers={'Set-Cookie':cookie})
            except (ValueError,TypeError) as error:
                message=str(error)
                code='too_many' if 'wait' in message else 'password_length' if '12 to' in message else 'auth_error'
                self._send_json(429 if code=='too_many' else 400,{'error':message,'error_code':code})
            except Exception:
                self._send_json(503,{'error':'Authentication unavailable. Use local recovery.','error_code':'unavailable'})
            return False
        if self.command=='GET' and path=='/login':
            from auth_ui import login_page
            self._send(200,login_page().encode(),'text/html; charset=utf-8');return False
        if auth.authenticated(token):return True
        if self.command=='GET' and path in ('/','/dashboard.html'):
            from auth_ui import login_page
            self._send(200,login_page().encode(),'text/html; charset=utf-8')
        else:self._send_json(401,{'error':'Login required.','error_code':'login_required'})
        return False

    def _local_request(self):
        from urllib.parse import urlsplit
        host=self.headers.get('Host','')
        try:
            parsed=urlsplit('http://'+host)
            hostname=parsed.hostname or ''
            loopback=hostname.casefold()=='localhost' or ipaddress.ip_address(hostname).is_loopback
            if not loopback or parsed.port!=self.server.server_port or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
                return False
            if not ipaddress.ip_address(self.client_address[0]).is_loopback:return False
        except ValueError:return False
        origin=self.headers.get('Origin')
        return (not origin or origin=='http://'+host) and self.headers.get('Sec-Fetch-Site') not in ('cross-site','same-site')

    def log_message(self, fmt, *args):  # quieter logs
        print(f"  {self.address_string()} {fmt % args}")

    def _send(self, code: int, body: bytes, content_type: str = "application/json",extra_headers=None):
        try:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Frame-Options','DENY')
            for name,value in (extra_headers or {}).items():self.send_header(name,value)
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
            # A navigation or cancelled fetch is normal; there is no recipient.
            self.close_connection=True

    def _send_json(self, code: int, obj: dict):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def do_OPTIONS(self):
        if not self._local_request():return self._send_json(403,{'error':'Use the local SelfOS dashboard'})
        if not self._auth_guard():return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if not self._local_request():return self._send_json(403,{'error':'Use the local SelfOS dashboard'})
        if not self._auth_guard():return
        from urllib.parse import urlparse,parse_qs
        parsed_path=urlparse(self.path)
        if parsed_path.path == '/__knowledge_run__':
            origin=self.headers.get('Origin');host=self.headers.get('Host','')
            if (origin and origin!=f'http://{host}') or self.headers.get('Sec-Fetch-Site')=='cross-site':
                return self._send_json(403,{'error':'Use the local SelfOS dashboard'})
            return self._send_json(200, knowledge_run_status())
        if parsed_path.path in ('/__knowledge__','/__knowledge_item__','/__knowledge_source__'):
            origin=self.headers.get('Origin');host=self.headers.get('Host','')
            if (origin and origin!=f'http://{host}') or self.headers.get('Sec-Fetch-Site')=='cross-site':
                return self._send_json(403,{'error':'Knowledge is available from the local dashboard only'})
            from knowledge_library import list_knowledge,knowledge_detail,knowledge_source
            qs=parse_qs(parsed_path.query)
            try:
                if parsed_path.path=='/__knowledge__':
                    result=list_knowledge(VAULT,category=qs.get('category',['all'])[0],query=qs.get('query',[''])[0],
                        offset=int(qs.get('offset',['0'])[0]),limit=int(qs.get('limit',['50'])[0]))
                elif parsed_path.path=='/__knowledge_item__':
                    result=knowledge_detail(VAULT,qs.get('id',[''])[0],
                        source_offset=int(qs.get('source_offset',['0'])[0]))
                else:result=knowledge_source(VAULT,qs.get('id',[''])[0])
                return self._send_json(200,result)
            except KeyError as error:return self._send_json(404,{'error':str(error).strip("'")})
            except (ValueError,TypeError) as error:return self._send_json(400,{'error':str(error)})
        if self.path == '/__knowledge_settings__':
            from knowledge_service import get_status
            return self._send_json(200, get_status(VAULT))
        if self.path == '/__model_settings__':
            from model_settings import public_config
            return self._send_json(200, public_config(ROOT))
        if self.path in ("/", "/dashboard.html"):
            if DASHBOARD.exists():
                body = DASHBOARD.read_bytes()
                from dashboard_ui import STYLE, integrate_overall
                page=body.decode('utf-8')
                from knowledge_ui import refresh_controls
                page=refresh_controls(page)
                page=re.sub(r'<style id="selfos-visual-system">.*?</style>',lambda _:STYLE,page,count=1,flags=re.S)
                body=integrate_overall(page).encode('utf-8')
                from auth_ui import ACCOUNT_CONTROLS
                body=body.replace(b'</body>',ACCOUNT_CONTROLS.encode('utf-8')+b'</body>')
                body=body.replace(b"let lang = localStorage.getItem('selfos-lang') === 'en' ? 'en' : 'zh';",
                                  b"let lang = localStorage.getItem('selfos-lang') === 'zh' ? 'zh' : 'en';")
                from model_ui import CONTROLS
                if b'id="model-settings-entry"' not in body:
                    body=body.replace(b'</body>',CONTROLS.encode('utf-8')+b'</body>')
                self._send(200, body, "text/html; charset=utf-8")
            else:
                self._send_json(404, {"error": "dashboard.html not found — run harvest.py first"})
        elif self.path == "/__staging__":
            staging_dir = VAULT / "91_Staging"
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
            cmd = [sys.executable, "-u", str(ROOT / ("knowledge.py" if knowledge else "harvest.py"))]
            if full and not knowledge:
                cmd.append("--full")
            stop_file = None
            if knowledge:
                if qs.get('action', [''])[0] == 'rebuild':
                    cmd.append('--rebuild')
                with KNOWLEDGE_RUN_LOCK:
                    if KNOWLEDGE_RUN["stop_file"] is not None:
                        return self._send_json(409, {"error": "Knowledge import already running"})
                    stop_file = Path(tempfile.gettempdir()) / ("selfos-stop-" + uuid.uuid4().hex)
                    KNOWLEDGE_RUN.clear()
                    KNOWLEDGE_RUN.update(stop_file=stop_file, process=None, job_id=uuid.uuid4().hex,
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
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", cwd=str(ROOT),
                    bufsize=1
                )
                if knowledge:
                    with KNOWLEDGE_RUN_LOCK: KNOWLEDGE_RUN['process'] = proc
                for line in _process_lines(proc, _knowledge_run_line if knowledge else None):
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
                    with KNOWLEDGE_RUN_LOCK:
                        KNOWLEDGE_RUN["stop_file"] = None
                        KNOWLEDGE_RUN['process'] = None
                        KNOWLEDGE_RUN['result'] = outcome
                        KNOWLEDGE_RUN['phase'] = ('stopped' if outcome['cancelled'] else
                                                  'completed' if outcome['ok'] else 'failed')
                    stop_file.unlink(missing_ok=True)
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if not self._local_request():return self._send_json(403,{'error':'Use the local SelfOS dashboard'})
        if not self._auth_guard():return
        if self.path in ('/__model_settings__','/__model_test__'):
            with KNOWLEDGE_RUN_LOCK:
                if KNOWLEDGE_RUN['stop_file'] is not None:
                    return self._send_json(409,{'error':'Stop the current import before changing or testing models'})
                try:
                    from model_settings import save_config
                    from model_client import test_connection
                    body=json.loads(self._read_body())
                    if self.path=='/__model_settings__': result=save_config(ROOT,body)
                    else: result=test_connection(ROOT)
                    return self._send_json(200,result)
                except (ValueError,TypeError,KeyError) as error:
                    return self._send_json(400,{'error':str(error)})
                except RuntimeError as error:
                    return self._send_json(502,{'error':str(error)})
                except Exception:
                    return self._send_json(502,{'error':'Model connection failed; check endpoint, authentication, model and proxy'})
        if self.path in ('/__knowledge_settings__', '/__knowledge_restore__'):
            origin = self.headers.get('Origin')
            host = self.headers.get('Host', '')
            if (origin and origin != f'http://{host}') or self.headers.get('Sec-Fetch-Site') == 'cross-site':
                return self._send_json(403, {'error': 'Use the local SelfOS dashboard'})
            with KNOWLEDGE_RUN_LOCK:
                if KNOWLEDGE_RUN['stop_file'] is not None:
                    return self._send_json(409, {'error': 'Stop the current import before changing settings or restoring'})
                try:
                    body = json.loads(self._read_body())
                    from knowledge_service import save_settings, get_status, restore_last
                    if self.path == '/__knowledge_settings__':
                        save_settings(VAULT, body)
                    else:
                        if not isinstance(body.get('operation_id'), str):
                            raise ValueError('operation_id required')
                        restore_last(VAULT, body['operation_id'])
                    return self._send_json(200, get_status(VAULT))
                except (ValueError, TypeError, KeyError) as error:
                    return self._send_json(400, {'error': str(error)})
        if self.path == "/__knowledge_stop__":
            origin = self.headers.get("Origin")
            host = self.headers.get("Host", "")
            if (origin and origin != f"http://{host}") or self.headers.get("Sec-Fetch-Site") == "cross-site":
                return self._send_json(403, {"error": "Stop must be requested from the local dashboard"})
            with KNOWLEDGE_RUN_LOCK:
                marker = KNOWLEDGE_RUN["stop_file"]
                if marker is not None:
                    marker.touch()
            return self._send_json(200, {"ok": True, "running": marker is not None})
        if self.path == "/__harvest__":
            try:
                body = self._read_body()
                full = False
                if body:
                    try:
                        full = json.loads(body).get("full", False)
                    except Exception:
                        pass
                cmd = [sys.executable, str(ROOT / "harvest.py")]
                if full:
                    cmd.append("--full")
                result = subprocess.run(
                    cmd,
                    capture_output=True, text=True, timeout=120, cwd=str(ROOT)
                )
                ok = result.returncode == 0
                self._send_json(200 if ok else 500, {
                    "ok": ok,
                    "stdout": result.stdout[-2000:],
                    "stderr": result.stderr[-500:],
                })
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})

        elif self.path == "/__staging__/apply":
            try:
                body = json.loads(self._read_body())
                filenames = body.get("files", [])  # list of staging filenames to apply
                if not isinstance(filenames,list) or any(not isinstance(name,str) for name in filenames):
                    return self._send_json(400,{'error':'files must be an array of staging filenames'})
                staging_dir = (VAULT / "91_Staging").resolve()
                vault_dir=VAULT.resolve()
                applied = []
                errors = []
                for fname in filenames:
                    if any(char in fname for char in ('/',chr(92),':')) or Path(fname).suffix.casefold()!='.md' or not staging_dir.is_relative_to(vault_dir):
                        errors.append(f'{fname}: invalid staging filename')
                        continue
                    staging_path = (staging_dir / fname).resolve()
                    if staging_path.parent!=staging_dir:
                        errors.append(f'{fname}: staging source leaves its directory')
                        continue
                    if not staging_path.exists():
                        errors.append(f"{fname}: not found")
                        continue
                    text = staging_path.read_text(encoding="utf-8", errors="replace")
                    # parse frontmatter to find target
                    target = ""
                    content_start = 0
                    lines = text.splitlines(keepends=True)
                    if lines and lines[0].strip() == "---":
                        for i, line in enumerate(lines[1:], 1):
                            if line.strip() == "---":
                                content_start = i + 1
                                break
                            if line.startswith("target:"):
                                target = line.split(":", 1)[1].strip()
                    if not target:
                        errors.append(f"{fname}: no target in frontmatter")
                        continue
                    target_path = (ROOT / target).resolve()
                    if Path(target).is_absolute() or ':' in target or not target_path.is_relative_to(vault_dir) or target_path.is_relative_to(staging_dir) or target_path.suffix.casefold()!='.md':
                        errors.append(f'{fname}: target must be canonical markdown inside the vault')
                        continue
                    if any(part.startswith('.') for part in target_path.relative_to(vault_dir).parts):
                        errors.append(f'{fname}: target cannot be an internal vault file')
                        continue
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    # write content after frontmatter
                    content = "".join(lines[content_start:]).lstrip("\n")
                    target_path.write_text(content, encoding="utf-8")
                    staging_path.unlink()
                    applied.append(fname)
                self._send_json(200, {"ok": True, "applied": applied, "errors": errors})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})

        elif self.path == "/chat":
            try:
                body = json.loads(self._read_body())
                messages = body.get("messages", [])
                if not messages:
                    return self._send_json(400, {"error": "messages required"})

                api_key, base_url = _get_config()
                if not api_key and __import__('model_settings').load_config(ROOT)['provider']=='anthropic':
                    return self._send_json(500, {
                        "error": "ANTHROPIC_API_KEY not set. Add it to .env or export it."
                    })

                reply = _call_claude(messages, api_key, base_url)
                self._send_json(200, {"reply": reply})

            except URLError as e:
                self._send_json(502, {"error": f"API error: {e}"})
            except Exception as e:
                self._send_json(500, {"error": str(e)})
        else:
            self._send_json(404, {"error": "not found"})


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7070)
    args = parser.parse_args()

    # Only run harvest on startup if dashboard.html doesn't exist yet
    if not DASHBOARD.exists():
        print("Building dashboard from local vault state; no conversation scan or model calls.")
        from harvest import generate_dashboard
        generate_dashboard(VAULT)
    else:
        print("dashboard.html found — skipping startup harvest (use ⟳ to refresh)")

    class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True

    server = ThreadedHTTPServer(("localhost", args.port), Handler)
    from selfos_auth import AuthManager
    server.auth=AuthManager(ROOT,VAULT)
    url = f"http://localhost:{args.port}"
    print(f"\nSelfOS running at {url}")

    import webbrowser
    webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
