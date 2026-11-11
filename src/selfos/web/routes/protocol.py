"""Protocol HTTP routes; no server imports."""
import json
import ipaddress

class ProtocolRoutes:
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
