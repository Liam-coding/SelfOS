"""Explicit canonical transaction boundary; callers hold the knowledge lock."""
import json
from datetime import datetime,timezone
from selfos.storage.pipeline import safe_path,recover,commit
from selfos.storage.change_receipts import HEAD_NAME,ROOT_LIMIT,read_json,receipt_folder,read_head,read_root,identity,sha,prepare_receipt
from selfos.knowledge.changes import compare_changes

def publish_changes(vault,writes,run_id,index,*,kind,action_id=None,state_after_tip=None,reverted_receipts=None):
    recover(vault)
    ident=identity(run_id,index)
    if HEAD_NAME in writes:raise ValueError('Audit head is owned by publication')
    write_hashes={name:sha(content) for name,content in writes.items()}
    for name in writes:safe_path(vault,name)
    names={'state':'.knowledge_pipeline.json','ledger':'.knowledge_corrections.json'}
    before={key:safe_path(vault,name).read_bytes() if safe_path(vault,name).exists() else None for key,name in names.items()}
    after={key:writes.get(name,before[key]) for key,name in names.items()}
    before_hashes={key:sha(content) for key,content in before.items()}
    after_hashes={key:sha(content) for key,content in after.items()}
    head=read_head(vault)
    if head and head['audit_tip']['run_id']==run_id and head['audit_tip']['index']==index:
        root=read_root(vault,head['audit_tip'])
        if root['after_hashes']!=after_hashes or root['kind']!=kind or root['action_id']!=action_id or root.get('write_hashes')!=write_hashes:
            raise ValueError('Repeated operation identity has different content')
        if head['hashes']!=before_hashes:raise ValueError('Current canonical state does not match change head')
        return
    if head:
        read_root(vault,head['audit_tip'])
        if head['hashes']!=before_hashes:raise ValueError('Current canonical state does not match change head')
    def decode(content):return json.loads(content) if content is not None else {}
    before_state,after_state=decode(before['state']),decode(after['state'])
    before_ledger,after_ledger=decode(before['ledger']),decode(after['ledger'])
    instant=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    prepared=receipt_folder(vault,ident)/'change-receipt.json'
    if prepared.exists():
        existing=read_json(prepared,ROOT_LIMIT)
        if existing.get('write_hashes')!=write_hashes or existing.get('before_hashes')!=before_hashes:
            raise ValueError('Repeated operation identity has different content')
        instant=existing['recorded_at']
    changes=compare_changes(before_state,after_state,before_ledger,after_ledger,as_of=instant,operation=kind,action_id=action_id)
    sources={**before_state.get('sources',{}),**after_state.get('sources',{})}
    head_content=prepare_receipt(vault,run_id=run_id,index=index,kind=kind,changes=changes,sources=sources,
        before_hashes=before_hashes,after_hashes=after_hashes,as_of=instant,head=head,action_id=action_id,
        state_after_tip=state_after_tip,reverted_receipts=reverted_receipts,write_hashes=write_hashes)
    # Head first is safe because the same journal restores every member on failure.
    commit(vault,{HEAD_NAME:head_content,**writes},run_id,index)
