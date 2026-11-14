"""Disposable opaque session-bound proof contexts, never portable knowledge."""
import copy
import hashlib
import secrets
import threading
import time
from selfos.storage.change_receipts import encode

TTL=15*60
MAX_CURSORS=128
CACHE_LIMIT=64*1024*1024
PART_LIMIT=4*1024*1024
_cache={}
_lock=threading.Lock()

class NavigationLimit(ValueError):
    code='history_navigation_limit'

def owner(vault,session):
    if not isinstance(session,str) or not session:raise ValueError('Authenticated session required')
    from pathlib import Path
    return hashlib.sha256(encode([str(Path(vault).resolve()),session])).hexdigest()

def _expire():
    for token in list(_cache):
        if time.monotonic()-_cache[token]['created']>TTL:del _cache[token]

def save(vault,session,context):
    # Pack independent items into bounded parts, avoiding one giant encoded cache body.
    base={key:value for key,value in context.items() if key not in ('proofs','reverted')}
    parts=[];items=[]
    for key,value in [('base',base)]+[('proof',item) for item in context.get('proofs',{}).items()]+[('reverted',item) for item in context.get('reverted',[])]:
        item=[key,value]
        if len(encode(items+[item]))>PART_LIMIT:
            if not items:raise NavigationLimit('History proof context entry limit exceeded')
            parts.append(encode(items));items=[]
        if len(encode([item]))>PART_LIMIT:raise NavigationLimit('History proof context entry limit exceeded')
        items.append(item)
    if items:parts.append(encode(items))
    size=sum(map(len,parts))
    if size>CACHE_LIMIT:raise NavigationLimit('History proof context limit exceeded')
    with _lock:
        _expire()
        if len(_cache)>=MAX_CURSORS or size+sum(entry['bytes'] for entry in _cache.values())>CACHE_LIMIT:
            raise NavigationLimit('History cursor cache limit reached; restart navigation')
        token=secrets.token_urlsafe(32)
        _cache[token]={'owner':owner(vault,session),'created':time.monotonic(),'parts':parts,'bytes':size}
        return token

def load(vault,session,token):
    import json
    with _lock:
        _expire()
        entry=_cache.get(token)
        if not entry or entry['owner']!=owner(vault,session):raise ValueError('Invalid or expired history cursor; restart navigation')
        context={'proofs':{},'reverted':[]}
        for part in entry['parts']:
            for kind,value in json.loads(part):
                if kind=='base':context.update(value)
                elif kind=='proof':context['proofs'][value[0]]=value[1]
                else:context['reverted'].append(value)
        return copy.deepcopy(context)
