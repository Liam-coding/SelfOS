"""Read only declared package UI resources; never resolve user paths or expressions."""
import json
import re
from functools import lru_cache
from importlib.resources import files

_INCLUDE = re.compile(r'@@SELFOS_RESOURCE:([^@]+)@@')
_VALUE = re.compile(r'@@SELFOS_VALUE:([a-zA-Z0-9_]+)@@')


@lru_cache(maxsize=1)
def _names():
    manifest = json.loads(files('selfos.resources').joinpath('web', 'manifest.json').read_text(encoding='utf-8'))
    return frozenset(manifest['resources'])


def _read(name, chain):
    if not isinstance(name, str) or name not in _names() or any(part in ('', '.', '..') for part in name.split('/')) or '\\' in name or ':' in name:
        raise ValueError('Unknown frontend resource')
    if name in chain or len(chain) > 32:
        raise ValueError('Cyclic frontend resource include')
    value = files('selfos.resources').joinpath('web', *name.split('/')).read_text(encoding='utf-8')
    return _INCLUDE.sub(lambda match: _read(match[1], (*chain, name)), value)


@lru_cache(maxsize=128)
def frontend_text(name):
    """Load and expand a declared template or asset from the application package."""
    return _read(name, ())


def render_ui(name, values):
    """Substitute caller-provided display values once, after package includes expand."""
    if not isinstance(values, dict):
        raise ValueError('Frontend values must be a mapping')
    def replace(match):
        if match[1] not in values:
            raise ValueError('Missing frontend template value: ' + match[1])
        return str(values[match[1]])
    return _VALUE.sub(replace, frontend_text(name))
