"""Native organization actions; preview construction has a separate owner."""
import hashlib
from selfos.app.harness_previews import prepare_native, resolve_native, _key, _cached
from selfos.app.knowledge_status import _state
from selfos.storage.harness_scans import acknowledge_scan

def organize_native(vault, identity, **kwargs):
    from selfos.app.knowledge import run_knowledge
    preview = resolve_native(vault, identity)
    if not preview['sessions']:
        return dict(status='completed', installed=False, model_calls=0, cached=True, operation_id=None)
    aliases = _state(vault).get('project_aliases', {})
    expected = {key:dict(cache_key=_key(session, aliases), policy_hash=preview['policy_hash'],
        fingerprint=hashlib.sha256((session['fingerprint'] + preview['policy_hash']).encode()).hexdigest())
        for key, session in zip(preview['part_ids'], preview['sessions'])}
    if all(_cached(_state(vault), receipt) for receipt in expected.values()):
        return dict(status='completed', installed=False, model_calls=0, cached=True, operation_id=None)
    result = run_knowledge(vault, roots=[], selected_sessions=preview['sessions'],
                          request_id=preview['id'], request_cap=12, native_preview_id=identity, **kwargs)
    if result.get('installed') or result.get('status') == 'completed':
        try:
            acknowledge_scan(vault, preview['entry'], preview['part_ids'], max_chars=preview['part_chars'], canonical=expected)
        except (ValueError, OSError) as error:
            result.update(native_acknowledgement_pending=True, native_acknowledgement_error=str(error))
            kwargs.get('progress', lambda _: None)('Knowledge saved; native checkpoint acknowledgement remains pending')
    return result
