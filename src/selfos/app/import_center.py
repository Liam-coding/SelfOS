"""Compose source, upload, job and publication metadata without starting work."""
from pathlib import Path

from selfos.sources.selection import load_sources, source_entries, allowed_source
from selfos.storage.import_center import scan_receipts
from selfos.storage.settings import load_settings
from selfos.app.knowledge_status import _state


def import_center_status(vault, config_root, *, run=None, offset=0, limit=50):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError('Invalid import center page')
    from selfos.app.import_status import publication_status
    from selfos.app.uploads import upload_status
    from selfos.providers.settings import public_config
    vault = Path(vault).resolve()
    receipts = scan_receipts(vault)
    diagnostics = list(receipts['diagnostics'])
    try:
        selection = load_sources(vault)
        entries = source_entries(selection)
    except (OSError, ValueError, TypeError):
        selection, entries = None, []
        diagnostics.append('source_metadata_unavailable')
    sources = []
    for entry in entries:
        path = Path(entry['path'])
        errors = []
        try:
            available = path.is_dir() if entry['kind'] == 'directory' else path.is_file()
            excluded = not allowed_source(path, selection)
        except (OSError, ValueError):
            available, excluded = False, True
            errors.append('source_location_unavailable')
            if 'source_location_unavailable' not in diagnostics:
                diagnostics.append('source_location_unavailable')
        scan = next((r for r in receipts['items'] if entry['path'] in r['sources']), None)
        sources.append(dict(**entry, available=available, excluded=excluded,
                            scan=scan, pending_parts=None, diagnostics=errors))
    uploads = dict(items=[], total=0, offset=offset, limit=limit, has_more=False)
    if (vault / '.knowledge_uploads').exists():
        try:
            uploads = upload_status(vault, offset, limit)
            uploads['has_more'] = offset + len(uploads['items']) < uploads['total']
            for row in uploads['items']:
                row['scan'] = next((r for r in receipts['items'] if row['id'] in r['sources']), None)
        except (OSError, ValueError, TypeError):
            diagnostics.append('upload_metadata_unavailable')
    try:
        publication = publication_status(vault, _state(vault), load_settings(vault))
    except (OSError, ValueError, TypeError, AttributeError):
        publication = dict(operations=[], published_operation=None, staging_is_provisional=True)
        diagnostics.append('publication_metadata_unavailable')
    config = public_config(config_root)
    model = {key: config.get(key) for key in ('provider', 'model', 'has_api_key')}
    job = {key: (run or {}).get(key, default) for key, default in
           [('running', False), ('phase', 'idle'), ('job_id', None), ('completed', 0), ('total', 0)]}
    return dict(sources=sources, uploads=uploads, job=job, publication=publication,
                model=model, diagnostics=diagnostics, scan_totals='bounded_preview_only')
