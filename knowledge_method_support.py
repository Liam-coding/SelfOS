"""Backward-compatible entry point; implementation lives in selfos."""
import os as _os
from pathlib import Path as _Path
import sys as _sys
_root = _Path(__file__).resolve().parent
_sys.path.insert(0, str(_root / 'src'))
_os.environ.setdefault('SELFOS_ROOT', str(_root))
from selfos._compat import attach as _attach
from selfos._legacy import EXPORTS as _EXPORTS
_attach(__name__, _EXPORTS['knowledge_method_support'])
