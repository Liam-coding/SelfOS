"""Atomic correction transactions over current generated knowledge."""
import json
from datetime import datetime, timezone
from pathlib import Path
import uuid


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
        ledger=create_action(state,before,request)
        backup=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:12]
        writes=record_writes(vault,state,corrections=ledger)
        writes['.knowledge_corrections.json']=json.dumps(ledger,ensure_ascii=False,indent=2).encode()
        commit(vault,writes,backup,1)
        identity=request['action_id'] if request['action']=='undo' else ledger['actions'][-1]['id']
        return {'action_id':identity,'backup_id':backup,'ok':True}
