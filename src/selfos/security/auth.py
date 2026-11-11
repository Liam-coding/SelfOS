"""security / auth responsibilities."""
import hashlib
import json
import os
import secrets
import sys
import tempfile
import threading
import time
from pathlib import Path
from argon2 import PasswordHasher, extract_parameters, Type
from argon2.exceptions import VerificationError, InvalidHashError
from selfos.paths import AppPaths, auth_directory

def private_path(path,directory=False):
    if os.name!='nt':path.chmod(0o700 if directory else 0o600)
    else:
        import csv,subprocess
        who=subprocess.run(['whoami','/user','/fo','csv','/nh'],capture_output=True,text=True,check=True)
        sid=next(csv.reader(who.stdout.strip().splitlines()))[-1]
        access='*'+sid+(':'+ '(OI)(CI)F' if directory else ':F')
        subprocess.run(['icacls',str(path),'/inheritance:r','/grant:r',access],capture_output=True,check=True)


class AuthManager:
    TTL=12*60*60
    def __init__(self,root,vault,directory=None):
        self.root=Path(root);self.vault=Path(vault)
        self.directory=Path(directory) if directory is not None else auth_directory()
        self.path=self.directory/'auth.json'
        self.marker=AppPaths.from_root(self.root).auth_marker
        self.lock=threading.RLock();self.sessions={};self.failures=[]
        self.hasher=PasswordHasher(time_cost=3,memory_cost=65536,parallelism=1,type=Type.ID)

    def _record(self):
        try:
            raw=self.path.read_bytes()
            if len(raw)>4096:return None
            record=json.loads(raw)
            if not isinstance(record,dict):return None
            if record.get('version')!=1 or not isinstance(record.get('hash'),str):return None
            params=extract_parameters(record['hash'])
            if params.type!=Type.ID or params.version!=19 or not 19456<=params.memory_cost<=262144 or not 2<=params.time_cost<=6 or not 1<=params.parallelism<=4 or params.salt_len<16 or params.hash_len<32:return None
            return record,hashlib.sha256(raw).hexdigest()
        except (OSError,ValueError,TypeError,KeyError,InvalidHashError):return None

    def status(self):
        with self.lock:
            if self._record():return 'ready'
            established=self.path.exists() or self.marker.exists() or (self.directory/'.initialized').exists()
            data=any((self.vault/n).exists() for n in ('.knowledge_pipeline.json','.knowledge_state.json','.knowledge_pending.json','SCORES.md'))
            data=data or any((self.vault/'90_Inbox').glob('*')) or any((self.vault/'02_Work/projects').glob('*.md'))
            # Conservatively protect existing Markdown, including manually maintained knowledge.
            data=data or any(p.is_file() and p.stat().st_size for p in self.vault.rglob('*.md'))
            return 'locked' if established or data else 'setup'

    def _password(self,password):
        if not isinstance(password,str) or not 12<=len(password)<=1024 or len(password.encode('utf-8'))>4096:
            raise ValueError('Use a password with 12 to 1024 characters.')

    def _write(self,password):
        self._password(password)
        encoded=self.hasher.hash(password)
        self.directory.mkdir(parents=True,exist_ok=True);private_path(self.directory,True)
        self.root.mkdir(parents=True,exist_ok=True)
        self.marker.write_text('Password authentication required.',encoding='utf-8')
        (self.directory/'.initialized').write_text('1',encoding='utf-8')
        fd,name=tempfile.mkstemp(dir=self.directory,prefix='.auth-',suffix='.tmp')
        path=Path(name)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f:
                json.dump({'version':1,'hash':encoded},f);f.flush();os.fsync(f.fileno())
            private_path(path)
            os.replace(path,self.path)
        finally:
            path.unlink(missing_ok=True)
        self.sessions.clear();self.failures.clear()

    def setup(self,password):
        with self.lock:
            if self.status()!='setup':raise ValueError('Authentication is already configured or locked. Use the local reset command.')
            self._write(password)

    def reset(self,password):
        with self.lock:self._write(password)

    def _verify(self,password):
        found=self._record()
        if found is None:raise ValueError('Authentication is locked. Use the local reset command.')
        if not isinstance(password,str) or len(password)>1024:raise ValueError('Incorrect password.')
        try:self.hasher.verify(found[0]['hash'],password)
        except (VerificationError,InvalidHashError):raise ValueError('Incorrect password.') from None
        return found[1]

    def login(self,password):
        with self.lock:
            now=time.monotonic();self.failures=[v for v in self.failures if now-v<60]
            if len(self.failures)>=5:raise ValueError('Too many attempts. Please wait one minute.')
            try:fingerprint=self._verify(password)
            except ValueError:self.failures.append(now);raise
            self.failures.clear()
            self.sessions={k:v for k,v in self.sessions.items() if v[0]>now}
            token=secrets.token_urlsafe(32)
            self.sessions[hashlib.sha256(token.encode()).hexdigest()]=(now+self.TTL,fingerprint)
            return token

    def authenticated(self,token):
        if not isinstance(token,str) or not token or len(token)>256:return False
        with self.lock:
            key=hashlib.sha256(token.encode()).hexdigest();session=self.sessions.get(key);found=self._record()
            valid=bool(session and found and session[0]>time.monotonic() and session[1]==found[1])
            if not valid:self.sessions.pop(key,None)
            return valid

    def logout(self,token):
        with self.lock:self.sessions.pop(hashlib.sha256(token.encode()).hexdigest(),None)

    def change(self,token,current,new):
        with self.lock:
            if not self.authenticated(token):raise ValueError('Please log in again.')
            self._verify(current);self._write(new)


def main():
    import argparse,getpass
    parser=argparse.ArgumentParser(description='Local SelfOS authentication recovery')
    parser.add_argument('action',choices=['reset'])
    from selfos.paths import project_root
    parser.add_argument('--root',type=Path,default=project_root())
    args=parser.parse_args()
    print('Reset the local login password. Existing sessions will be invalidated; knowledge is unchanged.')
    if input('Type RESET to continue: ')!='RESET':return
    password=getpass.getpass('New password (at least 12 characters): ')
    if password!=getpass.getpass('Confirm password: '):raise SystemExit('Passwords do not match.')
    AuthManager(args.root,args.root/'vault').reset(password)
    print('Password reset. Log in again. Restarting the server also clears sessions.')
