"""Versioned local JSON migration with explicit originals and backups."""
import base64
import json
from pathlib import Path, PurePosixPath
from selfos.storage.files import _atomic_write, _locked

MAX_BYTES = 64 * 1024 * 1024
CANONICAL = {'.knowledge_pipeline.json', '.knowledge_corrections.json', '.knowledge_settings.json', '.knowledge_sources.json'}
MODEL_FIELDS = ('provider','model','base_url','proxy_mode','proxy_url')


def _name(name):
    if not isinstance(name,str) or chr(92) in name or ':' in name:
        raise ValueError('Invalid package path')
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in ('','..','.') for p in name.split('/')):
        raise ValueError('Invalid package path')
    if name not in CANONICAL and not name.startswith(('.knowledge_uploads/originals/', '.knowledge_backups/')):
        raise ValueError('Unsupported package entry')
    return name


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
            raw = path.read_bytes(); total += len(raw)
            if total > MAX_BYTES: raise ValueError('Export exceeds 64 MiB')
            entries[name] = base64.b64encode(raw).decode('ascii')
        from selfos.providers.settings import public_config
        config = public_config(root)
        return {'format':'selfos-portable','version':1,'origin_vault':str(vault),
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
        try: raw = base64.b64decode(value,validate=True)
        except Exception: raise ValueError('Invalid package content') from None
        total += len(raw)
        if total > MAX_BYTES: raise ValueError('Import exceeds 64 MiB')
        if not (vault/name).resolve().is_relative_to(vault): raise ValueError('Import path escapes vault')
        decoded[name] = raw
    state = json.loads(decoded.get('.knowledge_pipeline.json',b'{}'))
    if not isinstance(state,dict) or not isinstance(state.get('sources',{}),dict): raise ValueError('Invalid knowledge state')
    if '.knowledge_sources.json' in decoded:
        from selfos.sources.selection import validate_selection
        validate_selection(json.loads(decoded['.knowledge_sources.json']))
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
    origin = package.get('origin_vault','')
    for identity, source in state.get('sources',{}).items():
        if not isinstance(source,dict): raise ValueError('Invalid source metadata')
        value = source.get('path','')
        if not isinstance(value,str): raise ValueError('Invalid source path')
        path = Path(value)
        relative = None
        if not path.is_absolute(): relative = path.as_posix()
        elif origin and path.is_relative_to(Path(origin)): relative = path.relative_to(Path(origin)).as_posix()
        if relative in decoded and relative.startswith('.knowledge_uploads/originals/'):
            source['path'] = str(vault/relative)
            source.setdefault('migration_original_path',value)
            status = 'resolved'
        else:
            target = path if path.is_absolute() else vault/path
            status = 'resolved' if target.is_file() else 'unresolved'
        report.append({'id':identity,'path':source.get('path',''),'status':status})
    if '.knowledge_sources.json' in decoded and origin:
        selection = json.loads(decoded['.knowledge_sources.json'])
        rebased = list(selection.get('privacy_exclusions', []))
        for field in ('exclusions','privacy_exclusions'):
            for rule in selection.get(field,[]):
                original_path = Path(rule)
                original_uploads = Path(origin)/'.knowledge_uploads/originals'
                if original_path.is_relative_to(original_uploads):
                    mapped = str(vault/'.knowledge_uploads/originals'/original_path.relative_to(original_uploads))
                    if mapped not in rebased: rebased.append(mapped)
        if rebased: selection['privacy_exclusions'] = rebased
        decoded['.knowledge_sources.json'] = json.dumps(selection,ensure_ascii=False,indent=2).encode()
    if '.knowledge_pipeline.json' in decoded:
        decoded['.knowledge_pipeline.json'] = json.dumps(state,ensure_ascii=False,indent=2).encode()
    if vault.exists() and any((vault/name).exists() for name in CANONICAL):
        raise ValueError('Import requires an empty knowledge destination')
    with _locked(vault):
        if any((vault/name).exists() for name in CANONICAL | set(decoded)): raise ValueError('Import destination changed')
        written = []
        try:
            for name, raw in decoded.items():
                _atomic_write(vault/name,raw)
                written.append(vault/name)
        except BaseException:
            for path in written: path.unlink(missing_ok=True)
            raise
        if config: _atomic_write(root/'.selfos-model.json',json.dumps({**config,'api_key':''}).encode())
        return {'imported':len(decoded),'sources':report,'credentials_imported':False}
