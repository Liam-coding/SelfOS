"""Immutable, hash-bound audit payloads; only the canonical head publishes them."""
import hashlib
import json
import re
from pathlib import Path
from selfos.storage.files import _atomic_write

HEAD_NAME='.knowledge_change_head.json'
HEAD_LIMIT=64*1024
ROOT_LIMIT=1024*1024
PART_LIMIT=4*1024*1024
AUDIT_LIMIT=64*1024*1024

def encode(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')

def sha(content):
    return hashlib.sha256(content).hexdigest() if content is not None else None

def identity(run_id,index):
    if not isinstance(run_id,str) or not re.fullmatch(r'[0-9]{8}T[0-9]{6}-[a-f0-9]{12}',run_id):
        raise ValueError('Invalid change operation identity')
    if isinstance(index,bool) or not isinstance(index,int) or not 0<=index<=999999:
        raise ValueError('Invalid change operation index')
    return {'run_id':run_id,'index':index}

def validate_ref(ref,*,hashed=True):
    if not isinstance(ref,dict) or set(ref)!=({'run_id','index','hash'} if hashed else {'run_id','index'}):
        raise ValueError('Invalid change reference')
    identity(ref['run_id'],ref['index'])
    if hashed and (not isinstance(ref['hash'],str) or not re.fullmatch('[a-f0-9]{64}',ref['hash'])):
        raise ValueError('Invalid change reference hash')
    return ref

def contained(vault,name):
    vault=Path(vault).resolve()
    path=vault/name
    if not path.resolve().is_relative_to(vault):raise ValueError('Change path escapes vault')
    return path

def receipt_folder(vault,ref):
    identity(ref['run_id'],ref['index'])
    return contained(vault,'.knowledge_backups/'+ref['run_id']+'/'+f"{ref['index']:06d}")

def read_json(path,limit,expected=None):
    if path.stat().st_size>limit:raise ValueError('Change metadata byte limit exceeded')
    with path.open('rb') as stream:content=stream.read(limit+1)
    if len(content)>limit:raise ValueError('Change metadata byte limit exceeded')
    if expected is not None and sha(content)!=expected:raise ValueError('Change metadata hash mismatch')
    try:
        value=json.loads(content)
    except (ValueError,UnicodeError):raise ValueError('Invalid change metadata') from None
    if not isinstance(value,dict):raise ValueError('Invalid change metadata')
    return value

def read_head(vault):
    path=contained(vault,HEAD_NAME)
    if not path.exists():return None
    return validate_head(read_json(path,HEAD_LIMIT))

def validate_head(head):
    if head.get('version')!=1 or not isinstance(head.get('hashes'),dict):raise ValueError('Invalid change head')
    validate_ref(head.get('audit_tip'))
    if head.get('state_tip') is not None:validate_ref(head['state_tip'])
    if head.get('omitted_parent') is not None:validate_ref(head['omitted_parent'])
    for name in ('state','ledger'):
        value=head['hashes'].get(name)
        if value is not None and (not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value)):
            raise ValueError('Invalid canonical hash')
    return head

def read_root(vault,ref):
    validate_ref(ref)
    root=read_json(receipt_folder(vault,ref)/'change-receipt.json',ROOT_LIMIT,ref['hash'])
    return validate_root(root,ref)

def validate_root(root,ref):
    validate_ref(ref)
    if root.get('version')!=1 or root.get('identity')!=identity(ref['run_id'],ref['index']):
        raise ValueError('Invalid change root identity')
    if root.get('kind') not in ('import','correction','undo','restore'):raise ValueError('Invalid change operation kind')
    for field in ('audit_parent','state_before_tip'):
        if root.get(field) is not None:validate_ref(root[field])
    after=root.get('state_after_tip')
    if after is not None:validate_ref(after,hashed='hash' in after)
    parts=root.get('parts')
    if not isinstance(parts,list) or len(parts)>AUDIT_LIMIT//2:raise ValueError('Invalid change parts')
    total=0
    for number,part in enumerate(parts,1):
        if not isinstance(part,dict) or part.get('number')!=number or not isinstance(part.get('bytes'),int) or not 0<part['bytes']<=PART_LIMIT:
            raise ValueError('Invalid change part reference')
        validate_ref({**root['identity'],'hash':part.get('hash')})
        total+=part['bytes']
    if total+len(encode(root))>AUDIT_LIMIT:raise ValueError('Change operation byte limit exceeded')
    if not isinstance(root.get('change_count'),int) or root['change_count']<0:raise ValueError('Invalid change count')
    for reverted in root.get('reverted_receipts',[]):validate_ref(reverted)
    return root

def read_part(vault,ref,number):
    root=read_root(vault,ref)
    if isinstance(number,bool) or not isinstance(number,int) or not 1<=number<=len(root['parts']):
        raise ValueError('Invalid change part number')
    partref=root['parts'][number-1]
    path=receipt_folder(vault,ref)/f'changes-{number:06d}.json'
    if path.stat().st_size!=partref['bytes']:raise ValueError('Change part byte mismatch')
    part=read_json(path,PART_LIMIT,partref['hash'])
    if part.get('version')!=1 or not isinstance(part.get('changes'),list) or not isinstance(part.get('sources'),dict):
        raise ValueError('Invalid change part')
    return part

def write_immutable(path,content):
    if path.exists():
        if path.read_bytes()!=content:raise ValueError('Repeated operation identity has different content')
        return
    _atomic_write(path,content)

def prepare_receipt(vault,*,run_id,index,kind,changes,sources,before_hashes,after_hashes,as_of,head=None,
                    action_id=None,state_after_tip=None,reverted_receipts=None,write_hashes=None):
    ident=identity(run_id,index)
    if kind not in ('import','correction','undo','restore'):raise ValueError('Invalid change kind')
    parts=[]
    entries=[]
    metadata={}
    payloads=[]
    def flush():
        nonlocal entries,metadata
        if entries:
            payloads.append(encode({'version':1,'changes':entries,'sources':metadata}))
            entries=[];metadata={}
    for change in changes:
        added={key:sources[key] for key in change['source_ids'] if key in sources}
        candidate=encode({'version':1,'changes':entries+[change],'sources':{**metadata,**added}})
        if len(candidate)>PART_LIMIT:
            flush()
            candidate=encode({'version':1,'changes':[change],'sources':added})
            if len(candidate)>PART_LIMIT:raise ValueError('Change entry byte limit exceeded')
        entries.append(change);metadata.update(added)
    flush()
    for number,content in enumerate(payloads,1):parts.append({'number':number,'hash':sha(content),'bytes':len(content)})
    counts={}
    categories={}
    for change in changes:counts[change['action']]=counts.get(change['action'],0)+1
    for change in changes:categories[change['category']]=categories.get(change['category'],0)+1
    root={'version':1,'identity':ident,'kind':kind,'recorded_at':as_of,'action_id':action_id,
          'audit_parent':head['audit_tip'] if head else None,'state_before_tip':head['state_tip'] if head else None,
          'state_after_tip':state_after_tip if kind=='restore' else ident,'before_hashes':before_hashes,
          'after_hashes':after_hashes,'parts':parts,'change_count':len(changes),'counts':counts,
          'category_counts':categories,'conflict_count':sum(bool(change['conflict']) for change in changes),'reverted_receipts':reverted_receipts or [],
          'write_hashes':write_hashes or {}}
    content=encode(root)
    if len(content)>ROOT_LIMIT or len(content)+sum(map(len,payloads))>AUDIT_LIMIT:
        raise ValueError('Change operation byte limit exceeded')
    ref={**ident,'hash':sha(content)}
    next_head={'version':1,'audit_tip':ref,'state_tip':state_after_tip if kind=='restore' else ref,'hashes':after_hashes}
    if head and head.get('omitted_parent') is not None:next_head['omitted_parent']=head['omitted_parent']
    head_content=encode(next_head)
    if len(head_content)>HEAD_LIMIT:raise ValueError('Change head byte limit exceeded')
    folder=receipt_folder(vault,ref)
    write_immutable(folder/'change-receipt.json',content)
    for number,payload in enumerate(payloads,1):write_immutable(folder/f'changes-{number:06d}.json',payload)
    return head_content
