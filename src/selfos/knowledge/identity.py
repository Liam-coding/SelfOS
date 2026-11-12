"""knowledge / identity responsibilities."""


def unique(items):
    return list(dict.fromkeys(items))

import hashlib
import json
import re


def normalized(value):
    return re.sub(r'[\s_\-]+','',value).casefold()

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
