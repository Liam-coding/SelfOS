"""Load a durable correction ledger; malformed data must not disable corrections."""
import json
from pathlib import Path


def _strings(value):
    return isinstance(value,list) and all(isinstance(item,str) and item for item in value)


def _valid_action(action):
    if not isinstance(action,dict):return False
    category=action.get('category')
    originals=action.get('originals')
    patch=action.get('patch')
    allowed={'text','value'} if category in ('personal_facts','preferences') else {'text'}
    if (category not in ('projects','personal_facts','preferences','lessons','history')
        or action.get('action') not in ('edit','delete','merge')
        or any(not isinstance(action.get(k),str) or not action[k] for k in ('id','at'))
        or not isinstance(action.get('active',True),bool)
        or any(not _strings(action.get(k)) for k in ('anchors','versions','relation','dependencies'))
        or not action['versions'] or not action['relation']
        or not isinstance(originals,list) or not originals or len(originals)!=len(action['versions'])
        or not isinstance(patch,dict) or set(patch)-allowed
        or (action.get('action')!='delete' and not patch)
        or any(not isinstance(v,str) or not v.strip() or len(v)>2000 for v in patch.values())):
        return False
    for record in originals:
        if not isinstance(record,dict):return False
        if category=='projects' and not isinstance(record.get('project_id'),str):return False
        for field in ('source_ids','supporting_source_ids','context_source_ids','_correction_action_ids'):
            if field in record and not _strings(record[field]):return False
        observations=record.get('supporting_observations',[])
        if not isinstance(observations,list) or any(not isinstance(r,dict)
            or not isinstance(r.get('source_id'),str) or not isinstance(r.get('evidence',''),str) for r in observations):return False
    return True


def load_corrections(vault):
    from selfos.storage.pipeline import safe_path
    path=safe_path(Path(vault),'.knowledge_corrections.json')
    if not path.exists():return {'version':1,'actions':[]}
    if path.stat().st_size>32*1024*1024:raise ValueError('Correction ledger is too large')
    ledger=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(ledger,dict) or ledger.get('version')!=1 or not isinstance(ledger.get('actions'),list):
        raise ValueError('Invalid correction ledger')
    for action in ledger['actions']:
        if not _valid_action(action):
            raise ValueError('Invalid correction action')
    receipts=ledger.get('receipts',{})
    if not isinstance(receipts,dict) or any(not isinstance(r,dict) or set(r)!={'fingerprint','action_id','backup_id'}
        or any(not isinstance(v,str) for v in r.values()) for r in receipts.values()):
        raise ValueError('Invalid correction request receipts')
    return ledger
