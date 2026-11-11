"""storage / pipeline responsibilities."""
import hashlib
import json
import re
from pathlib import Path
import base64

def safe_path(vault, name):
    vault = Path(vault).resolve()
    if name not in (".knowledge_pipeline.json","05_Life/lessons.md","knowledge/personal_facts.md","knowledge/preferences.md","knowledge/history.md") and not re.fullmatch(r"02_Work/projects/[a-f0-9]{64}\.md", name):
        raise ValueError("unsupported pipeline path")
    path = vault / name
    if not path.resolve().is_relative_to(vault):
        raise ValueError("pipeline path escapes vault")
    return path


def recover(vault):
    from selfos.storage.files import _atomic_write
    vault = Path(vault).resolve()
    journal = vault / ".knowledge_pending.json"
    if journal.exists():
        for name, content in json.loads(journal.read_text()).items():
            path = safe_path(vault, name)
            if content is None:
                path.unlink(missing_ok=True)
            else:
                _atomic_write(path, base64.b64decode(content))
        journal.unlink()


def commit(vault, writes, run_id, index):
    from selfos.storage.files import _atomic_write
    vault = Path(vault).resolve()
    originals = {}
    for name in writes:
        path = safe_path(vault, name)
        originals[name] = base64.b64encode(path.read_bytes()).decode() if path.exists() else None
    folder = vault / ".knowledge_backups" / run_id / f"{index:06d}"
    if not folder.resolve().is_relative_to(vault):
        raise ValueError("backup path escapes vault")
    manifest = {name: {"before": originals[name], "after": hashlib.sha256(content).hexdigest() if content is not None else None} for name, content in writes.items()}
    _atomic_write(folder / "pipeline-manifest.json", json.dumps(manifest).encode())
    _atomic_write(vault / ".knowledge_pending.json", json.dumps(originals).encode())
    try:
        for name, content in writes.items():
            if content is None:
                safe_path(vault, name).unlink(missing_ok=True)
            else:
                _atomic_write(safe_path(vault, name), content)
    except BaseException:
        recover(vault)
        _atomic_write(folder / "rolled-back", b"1")
        raise
    (vault / ".knowledge_pending.json").unlink()


def restore_pipeline_backup(vault, run_id):
    from selfos.storage.files import _locked, _atomic_write
    vault = Path(vault).resolve()
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}-[a-f0-9]{12}", run_id):
        raise ValueError("invalid run id")
    with _locked(vault):
        recover(vault)
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
