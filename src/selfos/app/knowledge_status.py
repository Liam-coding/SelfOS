"""Read-only knowledge state and checkpoint queries shared by import and setup."""
import json
from pathlib import Path
from selfos.knowledge.settings import VERSION, policy_hash
from selfos.storage.settings import load_settings

def _state(vault):
    path = Path(vault) / '.knowledge_pipeline.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def get_status(vault):
    settings = load_settings(vault)
    state = _state(vault)
    from selfos.app.library import knowledge_counts
    from selfos.app.import_status import publication_status
    from selfos.storage.corrections import load_corrections
    from selfos.knowledge.corrections import apply_corrections
    return {'settings': settings, 'counts': knowledge_counts(apply_corrections(state,load_corrections(vault))),
        'publication': publication_status(vault, state, settings),
        'saved_checkpoints':len(_saved_summaries(Path(vault).resolve(),settings,lambda:False)),
        'last_operation': state.get('last_operation'),
        'needs_rebuild': bool(state) and (state.get('schema_version') != VERSION or
            state.get('policy_hash') != policy_hash(settings))}


def _saved_summaries(vault,settings,cancel):
    """Reuse exact unchanged sessions even when other conversations have grown."""
    cached={}
    for path in (vault/'.knowledge_rebuild').glob('*/.knowledge_pipeline.json'):
        if cancel():break
        if not path.resolve().is_relative_to(vault):continue
        try:
            state=json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(state,dict):continue
            if not state.get('policy') or policy_hash(state['policy'])!=policy_hash(settings):continue
            if not isinstance(state.get('cache',{}),dict) or not isinstance(state.get('summaries',{}),dict):continue
            for key,fingerprint in state.get('cache',{}).items():
                summary=state.get('summaries',{}).get(key)
                if isinstance(summary,dict):cached[(key,fingerprint)]=summary
        except (OSError,ValueError,TypeError,AttributeError):
            continue
    return cached


