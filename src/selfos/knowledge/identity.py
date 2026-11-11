"""knowledge / identity responsibilities."""


def unique(items):
    return list(dict.fromkeys(items))

import hashlib
import json

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
