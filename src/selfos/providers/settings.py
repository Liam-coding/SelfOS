"""providers / settings responsibilities."""
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.request import getproxies_environment, getproxies
from selfos.paths import AppPaths

FILE = '.selfos-model.json'


def _url(value, name):
    p = urlsplit(value)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError(f'{name} must be an HTTP(S) URL without credentials, query or fragment')
    try: p.port
    except ValueError: raise ValueError(f'Invalid {name} port')
    return value.rstrip('/')


def load_config(root):
    env = {}
    path = AppPaths.from_root(root).env_file
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k,v=line.split('=',1); env[k.strip()]=v.strip().strip('"').strip("'")
    env.update(os.environ)
    c = dict(provider='anthropic', model='', base_url=env.get('ANTHROPIC_BASE_URL','https://api.anthropic.com'),
             api_key=env.get('ANTHROPIC_API_KEY',''), proxy_mode='auto', proxy_url='')
    path = AppPaths.from_root(root).model_config
    if path.exists(): c.update(json.loads(path.read_text(encoding='utf-8')))
    return c


def resolve_config(root, patch):
    if not isinstance(patch,dict) or set(patch)-{'provider','model','base_url','api_key','proxy_mode','proxy_url','clear_api_key'}:
        raise ValueError('Unknown model settings')
    c=load_config(root)
    if patch.get('provider',c['provider']) != c['provider']:
        c.update(api_key='',model='gpt-4.1-mini' if patch['provider']=='openai' else 'claude-haiku-4-5-20251001',base_url='https://api.openai.com/v1' if patch['provider']=='openai' else 'https://api.anthropic.com')
    for k,v in patch.items():
        if k=='clear_api_key': continue
        if not isinstance(v,str) or len(v)>4096 or any(ord(x)<32 for x in v): raise ValueError(f'Invalid {k}')
        if k=='api_key' and not v: continue
        c[k]=v.strip()
    if patch.get('clear_api_key') is True: c['api_key']=''
    if c['provider'] not in ('anthropic','openai'): raise ValueError('Unsupported provider')
    if 'model' in patch and not c['model']: raise ValueError('Model name is required')
    c['base_url']=_url(c['base_url'],'Base URL')
    if c['proxy_mode'] not in ('auto','manual','direct'): raise ValueError('Unsupported proxy mode')
    if c['proxy_url']: c['proxy_url']=_url(c['proxy_url'],'Proxy URL')
    if c['proxy_mode']=='manual' and not c['proxy_url']: raise ValueError('Manual proxy URL is required')
    return c


def save_config(root, patch):
    c=resolve_config(root,patch)
    root=Path(root); root.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(dir=root,prefix='.selfos-model-',suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(c,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
        os.replace(name,AppPaths.from_root(root).model_config)
    finally:
        if os.path.exists(name): os.unlink(name)
    return public_config(root)


def proxy_info(c):
    if c['proxy_mode']=='direct': return {'source':'direct','proxies':{}}
    if c['proxy_mode']=='manual': return {'source':'manual','proxies':{'http':c['proxy_url'],'https':c['proxy_url']}}
    env=getproxies_environment()
    if any(env.get(k) for k in ('http','https','all')): return {'source':'environment','proxies':env}
    if os.name=='nt':
        from urllib.request import getproxies_registry
        system=getproxies_registry()
    else: system=getproxies()
    # Keep environment NO_PROXY when falling back to Windows registry settings.
    system.update(env)
    return {'source':'system' if any(system.get(k) for k in ('http','https')) else 'direct','proxies':system}


def public_config(root):
    c=load_config(root); info=proxy_info(c)
    public={k:v for k,v in c.items() if k!='api_key'}
    public.update(has_api_key=bool(c['api_key']),proxy_source=info['source'])
    # Never return credentials from environment/system proxies.
    public['effective_proxy']={k:urlunsplit((urlsplit(v).scheme,urlsplit(v).netloc.split('@')[-1],urlsplit(v).path,'',''))
                               for k,v in info['proxies'].items() if k in ('http','https','all')}
    return public
