"""Load a durable correction ledger; malformed data must not disable corrections."""
import json
from pathlib import Path


def load_corrections(vault):
    from selfos.storage.pipeline import safe_path
    path=safe_path(Path(vault),'.knowledge_corrections.json')
    if not path.exists():return {'version':1,'actions':[]}
    if path.stat().st_size>32*1024*1024:raise ValueError('Correction ledger is too large')
    ledger=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(ledger,dict) or ledger.get('version')!=1 or not isinstance(ledger.get('actions'),list):
        raise ValueError('Invalid correction ledger')
    for action in ledger['actions']:
        if not isinstance(action,dict) or any(field not in action for field in ('id','at','action','category','anchors','originals','relation')):
            raise ValueError('Invalid correction action')
        if action['action'] not in ('edit','delete','merge') or not isinstance(action['anchors'],list) or not isinstance(action['originals'],list):
            raise ValueError('Invalid correction action')
    return ledger
