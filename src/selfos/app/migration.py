"""Versioned local JSON migration with explicit originals and backups."""
import base64
import json
import os
import uuid
import re
import hashlib
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
    registry = re.fullmatch(r'\.knowledge_uploads/registry/[a-f0-9]{64}\.json', name)
    if name not in CANONICAL and not registry and not name.startswith(('.knowledge_uploads/originals/', '.knowledge_backups/')):
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
    from selfos.storage.upload_receipts import validate_receipts
    validate_receipts(state)


def _validate_uploaded_sources(state, decoded, origin, path_type):
    from selfos.sources.documents import NORMALIZATION_VERSION
    from selfos.sources.upload_text import MAX_NORMALIZED_BYTES
    from selfos.sources.text import redact
    normalized = {}
    for source_id, source in state.get('sources', {}).items():
        if not isinstance(source, dict):
            raise ValueError('Invalid uploaded source')
        if source.get('source') == 'opencode':
            if source_id != source.get('id'):
                raise ValueError('OpenCode source map identity mismatch')
            _validate_opencode_source(source, decoded, origin, path_type)
            continue
        if not any(key in source for key in ('document_id', 'normalization_version', 'text_start', 'text_end', 'text_sha256')):
            continue  # Legacy registered documents have no fragment coordinates.
        identity = source.get('document_id')
        if not isinstance(identity, str) or not re.fullmatch('[a-f0-9]{64}', identity):
            raise ValueError('Invalid uploaded document identity')
        registry_name = '.knowledge_uploads/registry/' + identity + '.json'
        if registry_name not in decoded:
            raise ValueError('Uploaded source has no admitted registry identity')
        row = json.loads(decoded[registry_name])
        if not isinstance(source.get('path'), str):
            raise ValueError('Invalid uploaded source path')
        path = path_type(source.get('path', ''))
        relative = path.as_posix() if not path.is_absolute() else (
            path.relative_to(path_type(origin)).as_posix() if origin and path.is_relative_to(path_type(origin)) else None)
        start, end = source.get('text_start'), source.get('text_end')
        if (source.get('source') != 'uploaded_file' or source.get('provenance') != 'quoted_dialogue'
                or source.get('timestamp_kind') != 'import_time' or relative != row['path']
                or source.get('content_sha256') != row['content_sha256']
                or source.get('normalization_version') != NORMALIZATION_VERSION
                or not isinstance(source.get('text_sha256'), str)
                or not re.fullmatch('[a-f0-9]{64}', source['text_sha256'])
                or type(start) is not int or type(end) is not int or not 0 <= start <= end <= MAX_NORMALIZED_BYTES):
            raise ValueError('Invalid uploaded source fragment binding')
        if relative in decoded:
            if identity not in normalized:
                text = redact(decoded[relative].decode('utf-8-sig'))
                normalized[identity] = (len(text), hashlib.sha256(text.encode('utf-8')).hexdigest())
            length, digest = normalized[identity]
            if end > length or source['text_sha256'] != digest:
                raise ValueError('Uploaded source fragment does not match its original')
    for identity, receipt in state.get('upload_processing', {}).items():
        from selfos.storage.upload_receipts import document_bound
        for part in receipt['parts'].values():
            if any(not document_bound(state.get('sources', {}).get(source_id, {}), identity, part['content_sha256'])
                   for source_id in part['source_ids']):
                raise ValueError('Uploaded processing receipt has unbound sources')


def _validate_opencode_source(source, decoded, origin, path_type):
    from selfos.sources.opencode_records import opencode_metadata
    from selfos.sources.opencode_export import parse_export, EXPORT_PROFILE
    def portable_path(value):
        if (not isinstance(value, str) or not value or len(value) > 4096
                or any(ord(c) < 32 for c in value) or not path_type(value).is_absolute()
                or '..' in path_type(value).parts):
            raise ValueError('Invalid portable OpenCode origin path')
        return value
    opencode_metadata(source, path_validator=portable_path)
    for locator in source['source_locators']:
        if locator['kind'] != 'document':
            continue
        identity = locator['document_id']
        registry = '.knowledge_uploads/registry/' + identity + '.json'
        if registry not in decoded:
            raise ValueError('OpenCode export source has no admitted original registry')
        row = json.loads(decoded[registry])
        path = path_type(locator['path'])
        relative = path.relative_to(path_type(origin)).as_posix() if origin and path.is_relative_to(path_type(origin)) else None
        if (row['profile'] != EXPORT_PROFILE or relative != row['path']
                or locator['content_sha256'] != row['content_sha256']
                or locator['original_filename'] != row['original_filename']
                or source.get('provenance') != 'quoted_dialogue'):
            raise ValueError('OpenCode export locator is not bound to its admitted original')
        if relative in decoded:
            # Parsing checks immutable bytes; a synthetic local path avoids resolving
            # a foreign storage origin as a host path. It is never opened.
            owned = {key:locator[key] for key in ('kind', 'document_id', 'content_sha256', 'original_filename')}
            owned['path'] = str(Path.cwd() / '.selfos-migration-original')
            parsed = parse_export(decoded[relative], owned)
            semantic = ('id', 'timestamp', 'role', 'source', 'project_id', 'session_id', 'provenance',
                        'cwd', 'native_project_id', 'native_session_id', 'native_message_id')
            if not any({k:v for k,v in message['source_locator'].items() if k != 'path'} ==
                       {k:v for k,v in locator.items() if k != 'path'} and
                       all(message.get(key) == source.get(key) for key in semantic)
                       for message in parsed['messages']):
                raise ValueError('OpenCode export locator does not match its original bytes')


def _validate_upload_entries(decoded):
    from selfos.storage.uploads import _entry, MAX_DOCUMENTS
    registry = [name for name in decoded if name.startswith('.knowledge_uploads/registry/')]
    if len(registry) > MAX_DOCUMENTS:
        raise ValueError('Imported upload registry exceeds limit')
    for name in registry:
        if len(decoded[name]) > 65536:
            raise ValueError('Imported upload registry exceeds size limit')
        row = _entry(json.loads(decoded[name]))
        if name != '.knowledge_uploads/registry/' + row['id'] + '.json':
            raise ValueError('Imported upload identity mismatch')
        raw = decoded.get(row['path'])
        if raw is not None:
            if len(raw) != row['size'] or hashlib.sha256(raw).hexdigest() != row['content_sha256']:
                raise ValueError('Imported original does not match its registry')
            try:
                text = raw.decode('utf-8-sig')
            except UnicodeDecodeError:
                raise ValueError('Imported original is not supported UTF-8') from None
            if chr(0) in text:
                raise ValueError('Imported original is not a text document')


def export_package(vault, root, *, include_originals=False, include_backups=False):
    if not isinstance(include_originals,bool) or not isinstance(include_backups,bool):
        raise ValueError('Export options must be boolean')
    vault = Path(vault).resolve()
    with _locked(vault):
        names = sorted(CANONICAL)
        if (vault / '.knowledge_uploads').exists():
            from selfos.storage.uploads import recover_uploads, upload_root, upload_path
            recover_uploads(vault)
            registry = upload_path(upload_root(vault), 'registry')
            if registry.exists():
                names += [p.relative_to(vault).as_posix() for p in registry.iterdir() if p.is_file()]
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
        _validate_upload_entries({name: base64.b64decode(value) for name, value in entries.items()})
        return {'format':'selfos-portable','version':1,'origin_vault':str(vault), 'origin_platform':os.name,
                'includes':{'originals':include_originals,'backups':include_backups,'credentials':False},
                'files':entries,'settings':{k:config[k] for k in MODEL_FIELDS if k in config}}


def _validate_foreign_selection(selection, path_type):
    """Validate portable permissions syntactically, without touching foreign paths."""
    if not isinstance(selection, dict) or selection.get('version', 1) not in (1, 2):
        raise ValueError('Invalid foreign source settings')
    typed = selection.get('version', 1) == 2
    if typed and set(selection) - {'version', 'roots', 'entries', 'exclusions', 'privacy_exclusions', 'project_exclusions'}:
        raise ValueError('Unsupported typed source fields')
    def paths(value, limit):
        if not isinstance(value, list) or len(value) > limit or any(
                not isinstance(p, str) or not p or len(p) > 4096 or any(ord(c) < 32 for c in p)
                or not path_type(p).is_absolute() or '..' in path_type(p).parts for p in value):
            raise ValueError('Invalid foreign source path list')
        return list(dict.fromkeys(path_type(p) for p in value))
    roots = paths(selection.get('roots', []), 20)
    databases = []
    if typed:
        entries = selection.get('entries')
        if not isinstance(entries, list) or len(entries) > 20:
            raise ValueError('Invalid foreign source entries')
        directories, seen = [], {}
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {'kind', 'path'} or entry['kind'] not in ('directory', 'opencode_database'):
                raise ValueError('Unsupported source adapter')
            path = paths([entry['path']], 1)[0]
            if path in seen and seen[path] != entry['kind']:
                raise ValueError('Source path has conflicting adapter kinds')
            if path not in seen:
                (directories if entry['kind'] == 'directory' else databases).append(path)
                seen[path] = entry['kind']
        if 'roots' in selection and roots != directories:
            raise ValueError('Compatibility roots must match directory entries')
        roots = directories
        paths(selection.get('project_exclusions', []), 100)
    exclusions = paths(selection.get('exclusions', []), 100)
    paths(selection.get('privacy_exclusions', []), 100)
    if any(not any(p.is_relative_to(root) for root in roots) and p not in databases for p in exclusions):
        raise ValueError('Invalid foreign exclusions')


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
    _validate_upload_entries(decoded)
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
    _validate_uploaded_sources(state, decoded, origin, origin_path)
    if '.knowledge_corrections.json' in decoded:
        from selfos.storage.corrections import validate_corrections
        validate_corrections(json.loads(decoded['.knowledge_corrections.json']))
    if '.knowledge_sources.json' in decoded:
        from selfos.sources.selection import validate_selection
        selection = json.loads(decoded['.knowledge_sources.json'])
        if foreign:
            _validate_foreign_selection(selection, origin_path)
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
        if source.get('source') == 'opencode':
            for locator in source.get('source_locators', []):
                original_locator = origin_path(locator['path'])
                local_relative = (original_locator.relative_to(origin_path(origin)).as_posix()
                                  if origin and original_locator.is_relative_to(origin_path(origin)) else None)
                if locator['kind'] == 'document' and local_relative in decoded:
                    locator['path'] = str(vault / local_relative).replace(chr(92), '/')
            primary = source.get('source_locator', {})
            matching = next((locator for locator in source['source_locators'] if
                locator.get('kind') == primary.get('kind') and locator.get('document_id') == primary.get('document_id')
                and locator.get('message_id') == primary.get('message_id')), None)
            if matching:
                source['source_locator'] = dict(matching)
                source['path'] = matching['path']
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
    from selfos.storage.uploads import upload_lock
    with _locked(vault), policy_lock(vault), upload_lock(vault):
        if any((vault/name).exists() for name in CANONICAL | set(decoded)): raise ValueError('Import destination changed')
        if config and (model_path.exists() or model_path.is_symlink()):
            raise ValueError('Import would replace existing model configuration')
        written = []
        try:
            for name, raw in decoded.items():
                _atomic_write(vault/name,raw)
                written.append((vault/name, (vault/name).stat(), hashlib.sha256(raw).hexdigest()))
            if config:
                _publish_model(model_path,json.dumps({**config,'api_key':''}).encode())
                written.append((model_path, model_path.stat(), hashlib.sha256(model_path.read_bytes()).hexdigest()))
        except BaseException:
            for path, original_stat, expected_hash in written:
                try:
                    current_stat = path.stat()
                    if (not path.is_symlink() and current_stat.st_ino == original_stat.st_ino
                            and current_stat.st_mtime_ns == original_stat.st_mtime_ns
                            and current_stat.st_size == original_stat.st_size
                            and hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash):
                        path.unlink()
                except OSError:
                    pass
            raise
        return {'imported':len(decoded),'sources':report,'credentials_imported':False}
