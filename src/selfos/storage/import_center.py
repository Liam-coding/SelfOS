"""Bounded scan metadata; never proof of canonical knowledge publication."""
import json
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from selfos.knowledge.identity import digest
from selfos.knowledge.settings import policy_hash
from selfos.sources.selection import load_sources, source_entries
from selfos.storage.settings import load_settings
from selfos.storage.files import _atomic_write, _locked

MAX_BYTES = 65536
FIELDS = {'preview_id', 'kind', 'sources', 'selection_hash', 'policy_hash', 'scanned_at', 'selected_parts', 'coverage', 'committed', 'status', 'diagnostics'}


def _path(vault):
    root = Path(vault).resolve()
    path = root / '.knowledge_import_center.json'
    if not path.resolve().is_relative_to(root):
        raise ValueError('Scan metadata escapes vault')
    return path


def scan_receipts(vault):
    try:
        path = _path(vault)
        if not path.exists():
            return {'items': [], 'diagnostics': []}
        with path.open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('Scan metadata exceeds allowance')
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('items'), list) or len(data['items']) > 100:
            raise ValueError('Invalid scan metadata')
        selection, policy = digest(load_sources(vault)), policy_hash(load_settings(vault))
        result = []
        for row in data['items']:
            if not isinstance(row, dict) or set(row) != FIELDS:
                raise ValueError('Invalid scan receipt')
            if (not isinstance(row['preview_id'], str) or not re.fullmatch('[a-f0-9]{32}', row['preview_id'])
                    or row['kind'] not in ('local', 'native', 'upload') or row['committed'] is not False
                    or type(row['selected_parts']) is not int or not 0 <= row['selected_parts'] <= 24
                    or row['coverage'] != 'bounded' or not isinstance(row['sources'], list) or len(row['sources']) > 20
                    or any(not isinstance(s, str) or len(s) > 4096 for s in row['sources'])
                    or not isinstance(row['scanned_at'], str) or len(row['scanned_at']) > 40
                    or datetime.fromisoformat(row['scanned_at']).tzinfo is None):
                raise ValueError('Invalid scan receipt fields')
            if (not isinstance(row['status'], str) or not re.fullmatch('[a-z_]{1,64}', row['status'])
                    or not isinstance(row['diagnostics'], list) or len(row['diagnostics']) > 20
                    or any(not isinstance(code, str) or not re.fullmatch('[a-z_]{1,64}', code) for code in row['diagnostics'])):
                raise ValueError('Invalid scan diagnostics')
            if row['selection_hash'] == selection and row['policy_hash'] == policy:
                result.append(row)
        return {'items': result, 'diagnostics': []}
    except (ValueError, OSError, TypeError, KeyError, UnicodeError):
        return {'items': [], 'diagnostics': ['scan_metadata_unavailable']}


def record_scan(vault, preview, kind):
    """Best effort: observability failure never changes preview admission."""
    try:
        selection = load_sources(vault)
        current_hash = digest(selection)
        admitted_hash = hashlib.sha256(json.dumps(selection, sort_keys=True).encode()).hexdigest() if kind == 'upload' else current_hash
        if preview.get('selection_hash', admitted_hash) != admitted_hash or preview['policy_hash'] != policy_hash(load_settings(vault)):
            return False
        if kind == 'local':
            paths = [Path(item['path']).resolve() for item in preview['files']]
            sources = [e['path'] for e in source_entries(selection) if e['kind'] == 'directory'
                       and (not paths or any(p.is_relative_to(Path(e['path'])) for p in paths))]
        elif kind == 'native':
            sources = [preview['entry']['path']]
        elif kind == 'upload':
            sources = preview['selected_ids']
        else:
            return False
        diagnostics = [item if isinstance(item, str) else item.get('code') if isinstance(item, dict) else None
                       for item in preview.get('diagnostics', [])]
        diagnostics = [code for code in diagnostics if isinstance(code, str) and re.fullmatch('[a-z_]{1,64}', code)][:20]
        row = dict(preview_id=preview['id'], kind=kind, sources=sources,
                   selection_hash=digest(selection), policy_hash=preview['policy_hash'],
                   scanned_at=datetime.now(timezone.utc).isoformat(),
                   selected_parts=len(preview['sessions']), coverage='bounded', committed=False,
                   status=preview.get('status', 'prepared'), diagnostics=diagnostics)
        path = _path(vault)
        root = Path(vault).resolve()
        lock_directory = root / '.knowledge_import_center'
        if (not lock_directory.resolve().is_relative_to(root)
                or not (lock_directory / '.knowledge.lock').resolve().is_relative_to(root)):
            return False
        with _locked(lock_directory):
            rows = [row, *[r for r in scan_receipts(vault)['items'] if r['preview_id'] != row['preview_id']]][:100]
            while rows:
                raw = json.dumps({'version': 1, 'items': rows}, ensure_ascii=False).encode('utf-8')
                if len(raw) <= MAX_BYTES:
                    _atomic_write(path, raw)
                    return True
                rows.pop()
        return False
    except (ValueError, OSError, TypeError, KeyError, RuntimeError):
        return False
