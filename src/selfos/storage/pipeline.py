"""Pipeline backup entry points and shared transaction exports."""
import hashlib
import json
import re
import base64
from pathlib import Path
from selfos.storage.transactions import safe_path, recover, commit

def restore_pipeline_backup(vault, run_id):
    from selfos.storage.files import _locked, _atomic_write
    vault = Path(vault).resolve()
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}-[a-f0-9]{12}", run_id):
        raise ValueError("invalid run id")
    with _locked(vault):
        recover(vault)
        from selfos.storage.change_receipts import read_head
        if read_head(vault) is not None:
            from selfos.storage.change_restore import restore_changes
            return restore_changes(vault,run_id)
        folder = vault / ".knowledge_backups" / run_id
        if not folder.resolve().is_relative_to(vault) or (folder / "restored").exists():
            raise ValueError("backup unavailable")
        simulated = {}
        manifests = sorted(folder.glob("*/pipeline-manifest.json"), reverse=True)
        if not manifests:
            raise ValueError("backup not found")
        for manifest in manifests:
            if (manifest.parent / "rolled-back").exists():
                continue
            for name, entry in json.loads(manifest.read_text()).items():
                path = safe_path(vault, name)
                content = simulated.get(name, path.read_bytes() if path.exists() else None)
                if (hashlib.sha256(content).hexdigest() if content is not None else None) != entry["after"]:
                    raise ValueError("file changed after import: " + name)
                simulated[name] = base64.b64decode(entry["before"]) if entry["before"] is not None else None
        # Journal restoration too, so a crash cannot leave half a restored cache.
        before = {n: base64.b64encode(safe_path(vault, n).read_bytes()).decode() if safe_path(vault,n).exists() else None for n in simulated}
        _atomic_write(vault / ".knowledge_pending.json", json.dumps(before).encode())
        for name, content in simulated.items():
            if content is None:
                safe_path(vault, name).unlink(missing_ok=True)
            else:
                _atomic_write(safe_path(vault, name), content)
        (vault / ".knowledge_pending.json").unlink()
        _atomic_write(folder / "restored", b"1")
