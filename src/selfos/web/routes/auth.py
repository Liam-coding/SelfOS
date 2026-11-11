"""Auth HTTP routes; no server imports."""
import json

class AuthRoutes:
    def _auth(self):
        if not hasattr(self.server,'auth'):
            from selfos.security.auth import AuthManager
            self.server.auth=AuthManager(self.runtime.ROOT,self.runtime.VAULT)
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
            from selfos.web.rendering.auth import login_page
            self._send(200,login_page().encode(),'text/html; charset=utf-8');return False
        if auth.authenticated(token):return True
        if self.command=='GET' and path in ('/','/dashboard.html'):
            from selfos.web.rendering.auth import login_page
            self._send(200,login_page().encode(),'text/html; charset=utf-8')
        else:self._send_json(401,{'error':'Login required.','error_code':'login_required'})
        return False
