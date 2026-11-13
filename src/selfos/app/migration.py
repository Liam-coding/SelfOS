"""Versioned local JSON migration with explicit originals and backups."""
import base64
import json
import os
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath
from selfos.storage.files import _atomic_write, _locked

MAX_BYTES = 64 * 1024 * 1024
CANONICAL = {'.knowledge_pipeline.json', '.knowledge_corrections.json', '.knowledge_settings.json', '.knowledge_sources.json', '.knowledge_migration.json'}
MODEL_FIELDS = ('provider','model','base_url','proxy_mode','proxy_url')


def _publish_model(path, raw):
    from selfos.providers.settings import config_lock
    with config_lock(path.parent):
        _publish_model_locked(path, raw)


def _publish_model_locked(path, raw):
    """Publish an existing durable file atomically, without replacing a key."""
    temporary = path.with_name('.selfos-model-migration-' + uuid.uuid4().hex + '.tmp')
    try:
        _atomic_write(temporary, raw)
        try:
            os.link(temporary, path)
        except FileExistsError:
            raise ValueError('Import would replace existing model configuration') from None
    except BaseException:
        # Remove our own partial publication, preserving concurrent replacements.
        try:
            if os.path.samefile(temporary, path):
                path.unlink()
        except OSError:
            pass
        raise
    finally:
        try: temporary.unlink(missing_ok=True)
        except OSError: pass


def _name(name):
    if not isinstance(name,str) or chr(92) in name or ':' in name:
        raise ValueError('Invalid package path')
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in ('','..','.') for p in name.split('/')):
        raise ValueError('Invalid package path')
    if name not in CANONICAL and not name.startswith(('.knowledge_uploads/originals/', '.knowledge_backups/')):
        raise ValueError('Unsupported package entry')
    return name


def _validate_state(state):
    if not isinstance(state, dict): raise ValueError('Invalid knowledge state')
    maps = ('sources', 'cards', 'summaries', 'cache', 'refined', 'project_aliases',
            'quality_sessions', 'quality_refinements')
    for field in maps:
        if not isinstance(state.get(field, {}), dict): raise ValueError('Invalid knowledge state map')
    def record(value):
        if not isinstance(value, dict): raise ValueError('Invalid knowledge record')
        for field in ('text', 'value', 'evidence', 'kind', 'domain', 'key', 'title',
                'intent', 'status', 'updated_at', 'observed_at', 'project_id', 'timestamp', 'role', 'source'):
            if field in value and not isinstance(value[field], str):
                raise ValueError('Invalid knowledge text field')
        for field in ('source_ids', 'supporting_source_ids', 'context_source_ids',
                'conflict_source_ids', 'superseded_by_source_ids', 'validity_source_ids'):
            if field in value and (not isinstance(value[field], list) or
                    any(not isinstance(identity, str) for identity in value[field])):
                raise ValueError('Invalid record sources')
        for field in ('revision', 'proposed_revision'):
            if value.get(field) is not None and not isinstance(value[field], dict):
                raise ValueError('Invalid record revision')
    def records(value):
        if not isinstance(value, list): raise ValueError('Invalid knowledge state list')
        for entry in value: record(entry)
    for field in ('lessons', 'personal_facts', 'preferences', 'history', 'records_history',
            'project_observations', 'project_observation_history', 'lesson_history',
            'retention_audit', 'review_diagnostics'):
        records(state.get(field, []))
    for card in state.get('cards', {}).values():
        record(card)
        for field in ('decisions', 'decision_history', 'blockers', 'next_steps'):
            if not isinstance(card.get(field, []), list) or any(not isinstance(v, str) for v in card.get(field, [])):
                raise ValueError('Invalid project card')
        for field in ('state_records', 'decision_records'): records(card.get(field, []))
    for summary in state.get('summaries', {}).values():
        record(summary)
        if summary.get('project') is not None: record(summary['project'])
        for field in ('lessons', 'personal_facts', 'preferences', 'history'): records(summary.get(field, []))
    for field in ('sources', 'quality_sessions', 'quality_refinements'):
        for entry in state.get(field, {}).values(): record(entry)
    # Validate the in-memory projection before any imported file is published.
    from selfos.app.library import _records, knowledge_counts
    try:
        _records(state)
        knowledge_counts(state)
    except (TypeError, AttributeError, KeyError, IndexError, ValueError):
        raise ValueError('Invalid knowledge consumer state') from None


def export_package(vault, root, *, include_originals=False, include_backups=False):
    if not isinstance(include_originals,bool) or not isinstance(include_backups,bool):
        raise ValueError('Export options must be boolean')
    vault = Path(vault).resolve()
    with _locked(vault):
        names = sorted(CANONICAL)
        for enabled, folder in ((include_originals,'.knowledge_uploads/originals'),(include_backups,'.knowledge_backups')):
            if enabled:
                names += [p.relative_to(vault).as_posix() for p in (vault/folder).rglob('*') if p.is_file()]
        entries = {}
        total = 0
        for name in names:
            path = (vault/_name(name)).resolve()
            if not path.is_relative_to(vault): raise ValueError('Export path escapes vault')
            if not path.is_file(): continue
            if path.stat().st_size > MAX_BYTES - total: raise ValueError('Export exceeds 64 MiB')
            with path.open('rb') as handle:
                raw = handle.read(MAX_BYTES - total + 1)
            total += len(raw)
            if total > MAX_BYTES: raise ValueError('Export exceeds 64 MiB')
            entries[name] = base64.b64encode(raw).decode('ascii')
        from selfos.providers.settings import public_config
        config = public_config(root)
        return {'format':'selfos-portable','version':1,'origin_vault':str(vault), 'origin_platform':os.name,
                'includes':{'originals':include_originals,'backups':include_backups,'credentials':False},
                'files':entries,'settings':{k:config[k] for k in MODEL_FIELDS if k in config}}


def import_package(vault, root, package):
    if not isinstance(package,dict) or package.get('format') != 'selfos-portable' or package.get('version') != 1:
        raise ValueError('Unsupported migration format')
    entries = package.get('files')
    config = package.get('settings',{})
    if not isinstance(entries,dict) or len(entries)>10000 or not isinstance(config,dict) or set(config)-set(MODEL_FIELDS):
        raise ValueError('Invalid migration package')
    vault = Path(vault).resolve(); root = Path(root).resolve()
    decoded = {}; total = 0
    for name,value in entries.items():
        _name(name)
        if not isinstance(value,str): raise ValueError('Invalid package content')
        if len(value) > ((MAX_BYTES - total + 2) // 3) * 4:
            raise ValueError('Import exceeds 64 MiB')
        try: raw = base64.b64decode(value,validate=True)
        except Exception: raise ValueError('Invalid package content') from None
        total += len(raw)
        if total > MAX_BYTES: raise ValueError('Import exceeds 64 MiB')
        if not (vault/name).resolve().is_relative_to(vault): raise ValueError('Import path escapes vault')
        decoded[name] = raw
    state = json.loads(decoded.get('.knowledge_pipeline.json',b'{}'))
    _validate_state(state)
    origin = package.get('origin_vault', '')
    if not isinstance(origin, str): raise ValueError('Invalid migration origin')
    platform = package.get('origin_platform')
    if platform is None:
        platform = 'nt' if origin and PureWindowsPath(origin).is_absolute() else 'posix' if origin and PurePosixPath(origin).is_absolute() else os.name
    if platform not in ('nt', 'posix'): raise ValueError('Unsupported migration origin platform')
    origin_path = PureWindowsPath if platform == 'nt' else PurePosixPath
    foreign = platform != os.name
    if '.knowledge_corrections.json' in decoded:
        from selfos.storage.corrections import validate_corrections
        validate_corrections(json.loads(decoded['.knowledge_corrections.json']))
    if '.knowledge_sources.json' in decoded:
        from selfos.sources.selection import validate_selection
        selection = json.loads(decoded['.knowledge_sources.json'])
        if foreign:
            if not isinstance(selection, dict) or selection.get('version', 1) != 1:
                raise ValueError('Invalid foreign source settings')
            for field, limit in (('roots',20), ('exclusions',100), ('privacy_exclusions',100)):
                paths = selection.get(field, [])
                if not isinstance(paths, list) or len(paths) > limit or any(
                        not isinstance(p, str) or not p or not origin_path(p).is_absolute() for p in paths):
                    raise ValueError('Invalid foreign source path list')
            if any(not any(origin_path(p).is_relative_to(origin_path(root)) for root in selection.get('roots', []))
                    for p in selection.get('exclusions', [])):
                raise ValueError('Invalid foreign exclusions')
            metadata = dict(version=1, origin_platform=platform, unresolved_selection=selection)
            decoded['.knowledge_migration.json'] = json.dumps(metadata, ensure_ascii=False, indent=2).encode()
        else:
            validate_selection(selection)
    if '.knowledge_settings.json' in decoded:
        from selfos.knowledge.settings import validate_settings
        validate_settings(json.loads(decoded['.knowledge_settings.json']))
    # Validate destination settings before any writes; the imported key is always empty.
    from selfos.providers.settings import _url
    if config.get('provider','anthropic') not in ('anthropic','openai'): raise ValueError('Invalid provider')
    if config.get('proxy_mode','auto') not in ('auto','manual','direct'): raise ValueError('Invalid proxy mode')
    for key in ('base_url','proxy_url'):
        if config.get(key): _url(config[key],key)
    if any(not isinstance(v,str) or len(v)>4096 for v in config.values()): raise ValueError('Invalid model settings')
    report = []
    for identity, source in state.get('sources',{}).items():
        if not isinstance(source,dict): raise ValueError('Invalid source metadata')
        value = source.get('path','')
        if not isinstance(value,str): raise ValueError('Invalid source path')
        path = origin_path(value)
        relative = None
        if not path.is_absolute(): relative = path.as_posix()
        elif origin and path.is_relative_to(origin_path(origin)): relative = path.relative_to(origin_path(origin)).as_posix()
        if relative in decoded and relative.startswith('.knowledge_uploads/originals/'):
            source['path'] = str(vault/relative)
            source.setdefault('migration_original_path',value)
            status = 'resolved'
        else:
            target = Path(value) if path.is_absolute() else vault / path.as_posix()
            status = 'resolved' if not foreign and target.is_file() else 'unresolved'
        report.append({'id':identity,'path':source.get('path',''),'status':status})
    if '.knowledge_sources.json' in decoded and origin:
        selection = json.loads(decoded['.knowledge_sources.json'])
        rebased = [] if foreign else list(selection.get('privacy_exclusions', []))
        for field in ('exclusions','privacy_exclusions'):
            for rule in selection.get(field,[]):
                original_path = origin_path(rule)
                original_uploads = origin_path(origin)/'.knowledge_uploads/originals'
                if original_path.is_relative_to(original_uploads):
                    mapped = str(vault/'.knowledge_uploads/originals'/original_path.relative_to(original_uploads).as_posix())
                    if mapped not in rebased: rebased.append(mapped)
        if foreign: selection = {'version':1, 'roots':[], 'exclusions':[]}
        if rebased: selection['privacy_exclusions'] = rebased
        validate_selection(selection)
        decoded['.knowledge_sources.json'] = json.dumps(selection,ensure_ascii=False,indent=2).encode()
    if '.knowledge_pipeline.json' in decoded:
        decoded['.knowledge_pipeline.json'] = json.dumps(state,ensure_ascii=False,indent=2).encode()
    if vault.exists() and any((vault/name).exists() for name in CANONICAL):
        raise ValueError('Import requires an empty knowledge destination')
    model_path = root / '.selfos-model.json'
    if config and (model_path.exists() or model_path.is_symlink()):
        raise ValueError('Import would replace existing model configuration')
    if not model_path.resolve().is_relative_to(root):
        raise ValueError('Model configuration path escapes root')
    from selfos.sources.selection import policy_lock
    with _locked(vault), policy_lock(vault):
        if any((vault/name).exists() for name in CANONICAL | set(decoded)): raise ValueError('Import destination changed')
        if config and (model_path.exists() or model_path.is_symlink()):
            raise ValueError('Import would replace existing model configuration')
        written = []
        try:
            for name, raw in decoded.items():
                written.append(vault/name)
                _atomic_write(vault/name,raw)
            if config:
                _publish_model(model_path,json.dumps({**config,'api_key':''}).encode())
                written.append(model_path)
        except BaseException:
            for path in written: path.unlink(missing_ok=True)
            raise
        return {'imported':len(decoded),'sources':report,'credentials_imported':False}
