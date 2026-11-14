"""web / server responsibilities."""
from selfos.app import chat
from selfos.app import jobs
import sys
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from selfos.paths import AppPaths, project_root
from selfos.web.routes.auth import AuthRoutes
from selfos.web.routes.protocol import ProtocolRoutes
from selfos.web.routes.dashboard import DashboardRoutes
from selfos.web.routes.actions import ActionsRoutes
from selfos.web.routes.uploads import UploadRoutes

ROOT = project_root()


VAULT = ROOT / "vault"


DASHBOARD = ROOT / "dashboard.html"


KNOWLEDGE_RUN = {"stop_file": None}


KNOWLEDGE_RUN_LOCK = threading.Lock()


STREAM_HEARTBEAT = 10


def knowledge_run_status():
    return jobs.knowledge_run_status(KNOWLEDGE_RUN, KNOWLEDGE_RUN_LOCK)


def _knowledge_run_line(line):
    return jobs.knowledge_run_line(line, KNOWLEDGE_RUN, KNOWLEDGE_RUN_LOCK)


def _process_lines(proc, on_line=None):
    return jobs.process_lines(proc, on_line, STREAM_HEARTBEAT)




def _load_vault_context():
    return chat.load_vault_context(VAULT)




def _get_config() -> tuple[str, str]:
    """Return (api_key, base_url) from env or .env file."""
    from selfos.providers.config import _get_api_config
    return _get_api_config(ROOT)


def _call_claude(messages, api_key, base_url):
    from selfos.app.privacy import request_scope, selection_hash
    with request_scope(VAULT, selection_hash(VAULT), []):
        return chat.call_model(messages, api_key, base_url, ROOT, _load_vault_context())



class Handler(AuthRoutes, ProtocolRoutes, DashboardRoutes, ActionsRoutes, UploadRoutes, BaseHTTPRequestHandler):
    # Composition context; routes receive the server runtime explicitly.
    runtime = sys.modules[__name__]


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=project_root())
    parser.add_argument("--port", type=int, default=7070)
    args = parser.parse_args()
    global ROOT, VAULT, DASHBOARD
    paths = AppPaths.from_root(args.root)
    ROOT, VAULT, DASHBOARD = paths.root, paths.vault, paths.dashboard
    ROOT.mkdir(parents=True, exist_ok=True)

    # Only run harvest on startup if dashboard.html doesn't exist yet
    if not DASHBOARD.exists():
        print("Building dashboard from local vault state; no conversation scan or model calls.")
        from selfos.web.rendering.dashboard import generate_dashboard
        generate_dashboard(VAULT)
    else:
        print("dashboard.html found — skipping startup harvest (use ⟳ to refresh)")

    class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True

    server = ThreadedHTTPServer(("localhost", args.port), Handler)
    from selfos.security.auth import AuthManager
    server.auth=AuthManager(ROOT,VAULT)
    url = f"http://localhost:{args.port}"
    print(f"\nSelfOS running at {url}")

    import webbrowser
    webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
