"""Verified inverse transactions retain a monotonic published audit chain."""
import base64
import uuid
from datetime import datetime,timezone
from selfos.storage.transactions import safe_path,recover
from selfos.storage.change_receipts import HEAD_NAME,ROOT_LIMIT,read_json,read_head,read_root,receipt_folder,sha,identity
from selfos.storage.change_publication import publish_changes

def restore_changes(vault,run_id):
    """Caller holds the knowledge lock; reverse the current contiguous state run."""
    identity(run_id,0)
    recover(vault)
    head=read_head(vault)
    if not head:raise ValueError('No verified audit state to restore')
    current=head['state_tip']
    if current is None or current['run_id']!=run_id:raise ValueError('Backup is unrelated or already reverted')
    simulated={}
    reverted=[]
    while current is not None and current['run_id']==run_id:
        if len(reverted)>=100:raise ValueError('Restore operation limit exceeded')
        root=read_root(vault,current)
        if root['kind']=='restore':raise ValueError('Cannot restore a restore transaction')
        if root['state_after_tip']!=root['identity']:raise ValueError('Invalid restore state ancestry')
        manifest=read_json(receipt_folder(vault,current)/'pipeline-manifest.json',64*1024*1024)
        if set(manifest)!={HEAD_NAME,*root['write_hashes']}:raise ValueError('Backup manifest differs from receipt')
        for name,entry in manifest.items():
            if name==HEAD_NAME:continue
            if not isinstance(entry,dict) or set(entry)!={'before','after'} or entry['after']!=root['write_hashes'][name]:
                raise ValueError('Invalid backup manifest hash')
            path=safe_path(vault,name)
            content=simulated[name] if name in simulated else path.read_bytes() if path.exists() else None
            if sha(content)!=entry['after']:raise ValueError('File changed after import: '+name)
            try:previous=base64.b64decode(entry['before'],validate=True) if entry['before'] is not None else None
            except (ValueError,TypeError):raise ValueError('Invalid backup bytes') from None
            simulated[name]=previous
        for key,name in (('state','.knowledge_pipeline.json'),('ledger','.knowledge_corrections.json')):
            path=safe_path(vault,name)
            content=simulated[name] if name in simulated else path.read_bytes() if path.exists() else None
            if sha(content)!=root['before_hashes'][key]:raise ValueError('Backup before state hash mismatch')
        # The original control record proves the predecessor state reference.
        original=manifest[HEAD_NAME]['before']
        import json
        previous_head=json.loads(base64.b64decode(original,validate=True)) if original is not None else None
        if (previous_head['state_tip'] if previous_head else None)!=root['state_before_tip']:
            raise ValueError('Backup state ancestry mismatch')
        reverted.append(current)
        current=root['state_before_tip']
    if current is not None:read_root(vault,current)
    restore_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:12]
    publish_changes(vault,simulated,restore_id,1,kind='restore',state_after_tip=current,reverted_receipts=reverted)
    return {'restored':run_id,'restore_id':restore_id,'reverted_receipts':reverted}
