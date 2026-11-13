"""Conservative source-based model input policy; local records remain intact."""
import copy
import hashlib
import json
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
from selfos.sources.selection import load_sources

_REQUEST_POLICY = ContextVar('selfos_privacy_request', default=None)


@contextmanager
def request_scope(vault, expected_hash, sources):
    token = _REQUEST_POLICY.set((vault,expected_hash,list(sources)))
    try:
        check_request_scope()
        yield
    finally:
        _REQUEST_POLICY.reset(token)


def check_request_scope():
    policy = _REQUEST_POLICY.get()
    if policy is not None: guard_request(*policy)


def selection_hash(vault):
    return hashlib.sha256(json.dumps(load_sources(vault), sort_keys=True).encode()).hexdigest()


def permitted_source(source, selection, vault):
    def resolved(value):
        path = Path(value)
        return (path if path.is_absolute() else Path(vault)/path).resolve()
    path = source.get('path')
    if not path: return False
    path = resolved(path)
    for field in ('path', 'project_id', 'project', 'cwd'):
        value = source.get(field)
        if value and any(resolved(value).is_relative_to(Path(rule)) for rule in selection['exclusions'] + selection.get('privacy_exclusions', [])):
            return False
    uploads = (Path(vault)/'.knowledge_uploads/originals').resolve()
    return path.is_relative_to(uploads) or any(path.is_relative_to(Path(root)) for root in selection['roots'])


def model_state(state, selection, vault):
    permitted = {identity for identity, source in state.get('sources', {}).items()
                 if permitted_source(source, selection, vault)}
    def supported(record):
        ids = record.get('source_ids', [])
        return bool(ids) and set(ids).issubset(permitted)
    result = copy.deepcopy(state)
    result['sources'] = {k:v for k,v in result.get('sources', {}).items() if k in permitted}
    result['cards'] = {k:v for k,v in result.get('cards', {}).items() if supported(v)}
    for field in ('lessons','lesson_history','personal_facts','preferences','history','records_history',
                  'project_observations','project_observation_history'):
        if field in result: result[field] = [r for r in result[field] if supported(r)]
    result['summaries'] = {k:v for k,v in result.get('summaries', {}).items()
        if all(supported(r) for r in ([v['project']] if v.get('project') else []) +
               [r for field in ('lessons','personal_facts','preferences','history') for r in v.get(field,[])])}
    return result


def guard_request(vault, expected_hash, sources):
    if selection_hash(vault) != expected_hash:
        raise ValueError('Privacy rules changed; restart the import')
    selection = load_sources(vault)
    if any(not permitted_source(source, selection, vault) for source in sources):
        raise ValueError('Request contains an excluded or unavailable source')


def privacy_status(vault, root):
    from selfos.providers.settings import public_config
    state_path = Path(vault)/'.knowledge_pipeline.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
    selection = load_sources(vault)
    withheld = sum(not permitted_source(s, selection, vault) for s in state.get('sources',{}).values())
    config = public_config(root)
    return {'selection':selection,'withheld_sources':withheld,
            'destination':{k:config.get(k,'') for k in ('provider','base_url','model')}}
