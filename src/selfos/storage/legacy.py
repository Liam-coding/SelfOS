"""storage / legacy responsibilities."""
from selfos.knowledge.contracts import SOURCES
from selfos.knowledge.contracts import STATE
from selfos.knowledge.contracts import TARGETS
import hashlib
import json
from pathlib import Path
import re
from selfos.storage.files import _atomic_write
from selfos.storage.files import _locked
from selfos.storage.files import _read_json

def _safe_path(vault, name):
    if name not in (*TARGETS, STATE, SOURCES):
        raise ValueError(f'Unsupported knowledge target: {name}')
    path = vault / name
    if not path.resolve().is_relative_to(vault.resolve()):
        raise ValueError('Knowledge target escapes vault')
    return path


def _backup_dir(vault, run_id):
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}-[a-f0-9]{12}', run_id):
        raise ValueError('Invalid backup ID')
    path = vault / '.knowledge_backups' / run_id
    if not path.resolve().is_relative_to(vault.resolve()):
        raise ValueError('Backup path escapes vault')
    return path


def _commit(vault, run_id, batch_number, writes):
    folder = _backup_dir(vault, run_id) / f'{batch_number:06d}'
    folder.mkdir(parents=True, exist_ok=False)
    originals, manifest = {}, {}
    for name, data in writes.items():
        path = _safe_path(vault, name)
        before = path.read_bytes() if path.exists() else None
        originals[name] = before
        manifest[name] = {'existed': before is not None, 'after': hashlib.sha256(data).hexdigest()}
        if before is not None:
            _atomic_write(folder / name, before)
    _atomic_write(folder / 'manifest.json', json.dumps(manifest).encode('utf-8'))
    touched = []
    try:
        for name, data in writes.items():
            _atomic_write(_safe_path(vault, name), data)
            touched.append(name)
    except Exception:
        for name in reversed(touched):
            path = _safe_path(vault, name)
            if originals[name] is None:
                path.unlink(missing_ok=True)
            else:
                _atomic_write(path, originals[name])
        _atomic_write(folder / 'rolled-back', b'1')
        raise


def restore_backup(vault, run_id):
    """Restore an import only if its files have not subsequently been changed."""
    vault = Path(vault).resolve()
    with _locked(vault):
        folder = _backup_dir(vault, run_id)
        manifests = sorted(folder.glob('*/manifest.json'), reverse=True)
        if not manifests or (folder / 'restored').exists():
            raise ValueError('Backup not found or already restored')
        simulated, restore = {}, {}
        for manifest_path in manifests:
            if (manifest_path.parent / 'rolled-back').exists():
                continue
            manifest = _read_json(manifest_path, {})
            for name, info in manifest.items():
                path = _safe_path(vault, name)
                current = simulated.get(name, path.read_bytes() if path.exists() else None)
                if current is None or hashlib.sha256(current).hexdigest() != info['after']:
                    raise ValueError(f'{name} changed after this import; restore newer imports first or compare the backup manually')
                snapshot = manifest_path.parent / name
                before = snapshot.read_bytes() if info['existed'] else None
                simulated[name] = restore[name] = before
        for name, before in restore.items():
            path = _safe_path(vault, name)
            if before is None:
                path.unlink(missing_ok=True)
            else:
                _atomic_write(path, before)
        _atomic_write(folder / 'restored', b'1')
