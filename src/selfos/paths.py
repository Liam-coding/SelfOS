"""Data locations are independent of installed code and resource locations."""
from dataclasses import dataclass
from importlib.resources import files
import os
import sys
from pathlib import Path

def canonical_path(path):
    """Resolve filesystem links and normalize Windows extended-path spelling."""
    resolved = Path(path).resolve()
    if os.name == 'nt':
        text = str(resolved)
        prefix = chr(92) * 2 + '?' + chr(92)
        if text.startswith(prefix + 'UNC' + chr(92)):
            text = chr(92) * 2 + text[len(prefix) + 4:]
        elif text.startswith(prefix):
            text = text[len(prefix):]
        resolved = Path(text)
    return resolved

def project_root():
    return Path(os.environ.get('SELFOS_ROOT', Path.cwd())).expanduser().resolve()

def auth_directory():
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'SelfOS'
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/SelfOS'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'selfos'

@dataclass(frozen=True)
class AppPaths:
    root: Path

    @classmethod
    def from_root(cls, root=None):
        return cls(Path(root).expanduser().resolve() if root is not None else project_root())

    @property
    def vault(self): return self.root / 'vault'
    @property
    def dashboard(self): return self.root / 'dashboard.html'
    @property
    def model_config(self): return self.root / '.selfos-model.json'
    @property
    def env_file(self): return self.root / '.env'
    @property
    def auth_marker(self): return self.root / '.selfos-auth-required'

def resource(*parts):
    return files('selfos.resources').joinpath(*parts)
