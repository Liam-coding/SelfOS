"""Organization request allowances; monetary pricing is intentionally deferred."""
import hashlib
import json
from selfos.providers.settings import load_config
from selfos.storage.files import _atomic_write
from selfos.storage.usage import _path, _read, _validate_budget


def model_identity(root):
    return config_identity(load_config(root))


def config_identity(config):
    fields = {key: config[key] for key in ('provider', 'model', 'base_url')}
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def read_budget(vault, config_root):
    stored = _read(_path(vault, '.knowledge_budget.json'), None, 65536)
    if stored is None:
        return _validate_budget({})
    if not isinstance(stored, dict) or stored.get('version') != 1 or set(stored) - {'version', 'model_identity', 'max_requests', 'input_price', 'output_price'}:
        raise ValueError('Invalid saved organization budget')
    return _validate_budget({'max_requests': stored.get('max_requests', 100)})


def save_budget(vault, config_root, patch):
    _validate_budget(patch)
    old = read_budget(vault, config_root)
    value = _validate_budget({**old, **patch})
    stored = {**value, 'version': 1}
    _atomic_write(_path(vault, '.knowledge_budget.json'), json.dumps(stored).encode())
    return read_budget(vault, config_root)
