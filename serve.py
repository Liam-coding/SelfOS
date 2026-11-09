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
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent
VAULT = ROOT / "vault"
DASHBOARD = ROOT / "dashboard.html"

# ── Vault context ──────────────────────────────────────────────────────────────

_CONTEXT_FILES = [
    "PROFILE.md",
    "NOW.md",
    "GOALS.md",
    "DECISIONS.md",
]

def _load_vault_context() -> str:
    parts = []
    for name in _CONTEXT_FILES:
        p = VAULT / name
        if p.exists():
            text = p.read_text(encoding="utf-8").strip()
            if text:
                parts.append(f"## {name}\n{text}")
    # also include latest digest if available
    inbox = VAULT / "90_Inbox"
    if inbox.exists():
        digests = sorted(inbox.glob("*-sessions-digest.md"), reverse=True)
        if digests:
            text = digests[0].read_text(encoding="utf-8").strip()
            if text:
                parts.append(f"## Latest Session Digest ({digests[0].name})\n{text[:4000]}")
    return "\n\n---\n\n".join(parts)


SYSTEM_PROMPT = """You are a personal AI assistant embedded in SelfOS — the user's second brain.
You have access to the user's vault: their profile, current priorities, goals, decisions, and session history.
Answer questions about the user's life, work, research, health, learning, and goals based on this context.
Be concise, direct, and personal. Speak as if you know them well — because you do.
If something is not in the context, say so honestly rather than guessing.

Vault context:
{context}"""

# ── API call ───────────────────────────────────────────────────────────────────

def _get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        env_file = ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("ANTHROPIC_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return key


def _call_claude(messages: list[dict], api_key: str) -> str:
    context = _load_vault_context()
    system = SYSTEM_PROMPT.format(context=context)

    payload = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 1024,
        "system": system,
        "messages": messages,
    }).encode()

    req = Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["content"][0]["text"]


# ── HTTP handler ───────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter logs
        print(f"  {self.address_string()} {fmt % args}")

    def _send(self, code: int, body: bytes, content_type: str = "application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, obj: dict):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/", "/dashboard.html"):
            if DASHBOARD.exists():
                body = DASHBOARD.read_bytes()
                self._send(200, body, "text/html; charset=utf-8")
            else:
                self._send_json(404, {"error": "dashboard.html not found — run harvest.py first"})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/__harvest__":
            try:
                result = subprocess.run(
                    [sys.executable, str(ROOT / "harvest.py")],
                    capture_output=True, text=True, timeout=60, cwd=str(ROOT)
                )
                ok = result.returncode == 0
                self._send_json(200 if ok else 500, {
                    "ok": ok,
                    "stdout": result.stdout[-2000:],
                    "stderr": result.stderr[-500:],
                })
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})

        elif self.path == "/chat":
            try:
                body = json.loads(self._read_body())
                messages = body.get("messages", [])
                if not messages:
                    return self._send_json(400, {"error": "messages required"})

                api_key = _get_api_key()
                if not api_key:
                    return self._send_json(500, {
                        "error": "ANTHROPIC_API_KEY not set. Add it to .env or export it."
                    })

                reply = _call_claude(messages, api_key)
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

    server = HTTPServer(("localhost", args.port), Handler)
    url = f"http://localhost:{args.port}"
    print(f"SelfOS server running at {url}")
    print(f"  Dashboard : {url}/")
    print(f"  Chat API  : POST {url}/chat")
    print(f"  Harvest   : POST {url}/__harvest__")
    print("  Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
