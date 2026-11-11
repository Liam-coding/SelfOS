"""storage.settings responsibilities."""
import copy
import json
from pathlib import Path
from selfos.knowledge.settings import validate_settings, DEFAULT_SETTINGS

def load_settings(vault):
    path=Path(vault)/'.knowledge_settings.json'
    return validate_settings(json.loads(path.read_text(encoding='utf-8'))) if path.exists() else copy.deepcopy(DEFAULT_SETTINGS)

def save_settings(vault,value):
    from selfos.storage.files import _atomic_write
    value=validate_settings(value)
    path=Path(vault).resolve()/'.knowledge_settings.json'
    if not path.resolve().is_relative_to(Path(vault).resolve()):raise ValueError('Settings path escapes vault')
    _atomic_write(path,json.dumps(value,ensure_ascii=False,indent=2).encode())
    return value
