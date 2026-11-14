"""Explicit contiguous portable audit ranges, validated before destination writes."""
import json
from selfos.storage.change_receipts import (HEAD_NAME,HEAD_LIMIT,ROOT_LIMIT,PART_LIMIT,read_head,read_root,read_part,
    receipt_folder,sha,encode,validate_head,validate_root,validate_ref)

EXPORT_LIMIT=64*1024*1024

def audit_export(vault,*,mode='none',recent=20):
    if mode not in ('none','recent','all') or isinstance(recent,bool) or not isinstance(recent,int) or not 1<=recent<=10000:
        raise ValueError('Invalid audit export range')
    result={'files':{},'manifest':None,'summary':{'operations':0,'bytes':0,'earlier_history_omitted':False}}
    if mode=='none':return result
    head=read_head(vault)
    if head is None:return result
    ref=head['audit_tip'];included=[];files={};total=0;seen=set()
    boundary=head.get('omitted_parent')
    while ref is not None and ref!=boundary and (mode=='all' or len(included)<recent):
        key=(ref['run_id'],ref['index'])
        if key in seen or len(included)>=10000:raise ValueError('Audit export ancestry limit exceeded')
        seen.add(key)
        root=read_root(vault,ref)
        folder=receipt_folder(vault,ref)
        paths=[folder/'change-receipt.json']
        for part in root['parts']:
            read_part(vault,ref,part['number'])
            paths.append(folder/f"changes-{part['number']:06d}.json")
        for path in paths:
            size=path.stat().st_size
            if size>EXPORT_LIMIT-total:raise ValueError('Audit export byte limit exceeded; select a smaller range')
            raw=path.read_bytes();total+=len(raw)
            if total>EXPORT_LIMIT:raise ValueError('Audit export byte limit exceeded')
            files[path.relative_to(folder.parents[2]).as_posix()]=raw
        included.append(ref);ref=root['audit_parent']
    exported_head={**head,'omitted_parent':ref}
    raw=encode(exported_head);total+=len(raw)
    if total>EXPORT_LIMIT:raise ValueError('Audit export byte limit exceeded')
    files[HEAD_NAME]=raw
    manifest={'version':1,'included':included,'omitted_parent':ref}
    return {'files':files,'manifest':manifest,'summary':{'operations':len(included),'bytes':total,
            'earlier_history_omitted':ref is not None,'newest':included[0],'oldest':included[-1]}}

def validate_audit_import(decoded,manifest):
    if manifest is None:
        if HEAD_NAME in decoded:raise ValueError('Audit head requires a declared range')
        return None
    if not isinstance(manifest,dict) or set(manifest)!={'version','included','omitted_parent'} or manifest['version']!=1:
        raise ValueError('Invalid audit manifest')
    included=manifest['included'];boundary=manifest['omitted_parent']
    if not isinstance(included,list) or not 1<=len(included)<=10000:raise ValueError('Invalid audit included range')
    if boundary is not None:validate_ref(boundary)
    head_raw=decoded.get(HEAD_NAME)
    if head_raw is None or len(head_raw)>HEAD_LIMIT:raise ValueError('Missing or oversized audit head')
    head=validate_head(json.loads(head_raw))
    if head['audit_tip']!=included[0] or head.get('omitted_parent')!=boundary:raise ValueError('Audit manifest head mismatch')
    for key,name in (('state','.knowledge_pipeline.json'),('ledger','.knowledge_corrections.json')):
        if head['hashes'][key]!=sha(decoded.get(name)):raise ValueError('Audit canonical hash mismatch')
    seen=set();current=head['audit_tip']
    for ref in included:
        validate_ref(ref)
        if ref!=current or (ref['run_id'],ref['index']) in seen:raise ValueError('Invalid audit ancestry')
        seen.add((ref['run_id'],ref['index']))
        prefix='.knowledge_backups/'+ref['run_id']+'/'+f"{ref['index']:06d}/"
        raw=decoded.get(prefix+'change-receipt.json')
        if raw is None or len(raw)>ROOT_LIMIT or sha(raw)!=ref['hash']:raise ValueError('Missing or invalid audit root hash')
        root=validate_root(json.loads(raw),ref)
        count=0;counts={};categories={};conflicts=0
        for part in root['parts']:
            raw=decoded.get(prefix+f"changes-{part['number']:06d}.json")
            if raw is None or len(raw)>PART_LIMIT or len(raw)!=part['bytes'] or sha(raw)!=part['hash']:
                raise ValueError('Missing or invalid audit part hash')
            payload=json.loads(raw)
            if payload.get('version')!=1 or not isinstance(payload.get('changes'),list) or not isinstance(payload.get('sources'),dict):
                raise ValueError('Invalid audit part')
            for change in payload['changes']:
                if not isinstance(change,dict) or change.get('category') not in ('projects','personal_facts','preferences','lessons','history'):
                    raise ValueError('Invalid historical change')
                action=change.get('action')
                if action not in ('added','updated','removed','superseded','invalidated','merged','restored'):raise ValueError('Invalid change action')
                if not isinstance(change.get('before'),list) or not isinstance(change.get('after'),list):raise ValueError('Invalid change snapshots')
                for snapshot in change['before']+change['after']:
                    if not isinstance(snapshot,dict) or not isinstance(snapshot.get('record'),dict):raise ValueError('Invalid change snapshot')
                counts[action]=counts.get(action,0)+1
                category=change['category'];categories[category]=categories.get(category,0)+1
                conflicts+=bool(change.get('conflict'));count+=1
        if count!=root['change_count'] or counts!=root['counts'] or categories!=root['category_counts'] or conflicts!=root['conflict_count']:
            raise ValueError('Audit counts mismatch')
        current=root['audit_parent']
    if current!=boundary:raise ValueError('Audit range has an undeclared missing ancestor')
    return boundary
