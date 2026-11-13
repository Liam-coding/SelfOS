"""Shared local source selection and directory-prefix exclusions."""
from pathlib import Path
import os
from contextlib import contextmanager, ExitStack

from selfos.sources.conversations import local_roots
from selfos.storage.onboarding import read_metadata, write_metadata


@contextmanager
def policy_lock(vault):
    """Coordinate supported rule writes with canonical publication."""
    from selfos.storage.files import _locked
    vault = Path(vault).resolve()
    guard = vault / '.knowledge_policy_guard'
    if not guard.resolve().is_relative_to(vault):
        raise ValueError('Privacy guard escapes vault')
    with ExitStack() as stack:
        try: stack.enter_context(_locked(guard))
        except RuntimeError:
            raise ValueError('Privacy rules are being published; retry later') from None
        yield


def _paths(value, limit):
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError("Invalid source path list")
    result = []
    for item in value:
        if not isinstance(item, str) or not item or not Path(item).is_absolute():
            raise ValueError("Source paths must be absolute")
        path = str(Path(item).resolve())
        if path not in result:
            result.append(path)
    return result


def validate_selection(value, require_available=False):
    if not isinstance(value, dict) or value.get("version", 1) != 1:
        raise ValueError("Unsupported source settings")
    roots = _paths(value.get("roots"), 20)
    exclusions = _paths(value.get("exclusions", []), 100)
    if require_available and any(not Path(root).is_dir() for root in roots):
        raise ValueError("Custom source directories must exist")
    if any(not any(Path(item).is_relative_to(Path(root)) for root in roots) for item in exclusions):
        raise ValueError("Exclusions must be inside selected roots")
    result = {"version": 1, "roots": roots, "exclusions": exclusions}
    if value.get('privacy_exclusions'):
        result['privacy_exclusions'] = _paths(value['privacy_exclusions'], 100)
    return result


def load_sources(vault, defaults=None):
    value = read_metadata(vault, ".knowledge_sources.json")
    # Historical import provenance used this filename before source selection.
    legacy = isinstance(value,dict) and 'roots' not in value and all(
        isinstance(item,dict) and 'path' in item and 'source' in item for item in value.values())
    if value is None or legacy:
        roots = local_roots() if defaults is None else defaults
        value = {"version": 1, "roots": [str(Path(p).resolve()) for p in roots], "exclusions": []}
    return validate_selection(value)


def save_sources(vault, value):
    selected = validate_selection(value, require_available=True)
    with policy_lock(vault):
        write_metadata(vault, ".knowledge_sources.json", selected)
    return selected


def discover_sources(defaults=None):
    roots = local_roots() if defaults is None else defaults
    return [{"path": str(Path(p).resolve()), "available": Path(p).is_dir(),
             "source": "claude" if "claude" in str(p).lower() else "codex" if "codex" in str(p).lower() else "custom"}
            for p in roots]


def allowed_source(path, selection):
    resolved = Path(path).resolve()
    return (any(resolved.is_relative_to(Path(root)) for root in selection["roots"])
            and not any(resolved.is_relative_to(Path(excluded)) for excluded in selection["exclusions"] + selection.get("privacy_exclusions", [])))


def select_files(selection, file_limit=2, entry_limit=2000, max_bytes=8 * 1024 * 1024):
    """Bound enumeration before any conversation reads; never follow directory links."""
    found, warnings, seen, entries = [], [], set(), 0
    stack = [Path(root) for root in selection["roots"]]
    while stack and entries < entry_limit:
        directory = stack.pop()
        if not directory.is_dir() or not allowed_source(directory, selection):
            continue
        try:
            with os.scandir(directory) as iterator:
                for item in iterator:
                    entries += 1
                    if entries > entry_limit:
                        break
                    path = Path(item.path)
                    if item.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                        warnings.append({"code": "symlink", "path": str(path)})
                        continue
                    if not allowed_source(path, selection):
                        continue
                    if item.is_dir(follow_symlinks=False):
                        stack.append(path)
                    elif item.is_file(follow_symlinks=False) and path.suffix.lower() == ".jsonl":
                        stat = item.stat(follow_symlinks=False)
                        if stat.st_size > max_bytes:
                            warnings.append({"code": "oversize", "path": str(path)})
                        elif str(path.resolve()) not in seen:
                            seen.add(str(path.resolve()))
                            found.append((stat.st_mtime_ns, str(path.resolve())))
        except OSError:
            warnings.append({"code": "unavailable", "path": str(directory)})
    if stack or entries >= entry_limit:
        warnings.append({"code": "enumeration_limit"})
    found.sort(reverse=True)
    if len(found) > file_limit:
        warnings.append({"code": "file_limit"})
    return [Path(path) for _, path in found[:file_limit]], warnings
