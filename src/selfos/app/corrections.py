"""Atomic correction transactions over current generated knowledge."""
import json
from datetime import datetime, timezone
from pathlib import Path
import uuid
import re


def correct_knowledge(vault, request):
    from selfos.storage.files import _locked
    from selfos.storage.pipeline import safe_path, recover, commit
    from selfos.storage.corrections import load_corrections
    from selfos.storage.records import record_writes
    from selfos.knowledge.corrections import create_action
    vault=Path(vault).resolve()
    with _locked(vault):
        recover(vault)
        path=safe_path(vault,'.knowledge_pipeline.json')
        state=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        before=load_corrections(vault)
        from selfos.knowledge.identity import digest
        request_id=request.get('request_id') if isinstance(request,dict) else None
        if request_id is not None and (not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}',request_id)):
            raise ValueError('Invalid request identity')
        fingerprint=digest({k:v for k,v in request.items() if k!='request_id'}) if isinstance(request,dict) else ''
        receipt=before.get('receipts',{}).get(request_id)
        if receipt:
            if receipt['fingerprint']!=fingerprint:raise ValueError('Repeated request identity has different content')
            return {'action_id':receipt['action_id'],'backup_id':receipt['backup_id'],'ok':True}
        ledger=create_action(state,before,request)
        backup=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:12]
        identity=request['action_id'] if request['action']=='undo' else ledger['actions'][-1]['id']
        if request_id:ledger.setdefault('receipts',{})[request_id]={'fingerprint':fingerprint,'action_id':identity,'backup_id':backup}
        writes=record_writes(vault,state,corrections=ledger)
        writes['.knowledge_corrections.json']=json.dumps(ledger,ensure_ascii=False,indent=2).encode()
        from selfos.app.change_publication import publish_changes
        publish_changes(vault,writes,backup,1,kind='undo' if request['action']=='undo' else 'correction',action_id=identity)
        return {'action_id':identity,'backup_id':backup,'ok':True}


def correction_metadata(vault,identity=''):
    from selfos.storage.pipeline import safe_path
    from selfos.storage.corrections import load_corrections
    from selfos.knowledge.corrections import correction_options
    path=safe_path(vault,'.knowledge_pipeline.json')
    state=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    return correction_options(state,load_corrections(vault),identity)
