"""Metadata-only pinned OpenCode data-file discovery; never initialize SQLite."""
import os
from pathlib import Path


def discover_opencode(*, environ=None, home=None):
    environment = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    xdg = environment.get('XDG_DATA_HOME', '')
    data = Path(xdg) if isinstance(xdg, str) and xdg and Path(xdg).is_absolute() else home / '.local/share'
    root = (data / 'opencode').resolve()
    override = environment.get('OPENCODE_DB', '')
    candidate = dict(source='opencode', kind='opencode_database', available=False, path=None)
    if override == ':memory:':
        return [{**candidate, 'status': 'memory_unavailable'}]
    if not isinstance(override, str) or any(ord(char) < 32 for char in override):
        return [{**candidate, 'status': 'invalid_override'}]
    try:
        path = Path(override) if override else Path('opencode.db')
        if not path.is_absolute():
            path = (root / path).resolve()
            if not path.is_relative_to(root):
                return [{**candidate, 'status': 'invalid_override'}]
        else:
            path = path.resolve()
        available = path.is_file()
        return [{**candidate, 'path': str(path), 'available': available,
                 'status': 'available' if available else 'unavailable'}]
    except (OSError, ValueError):
        return [{**candidate, 'status': 'unavailable'}]
