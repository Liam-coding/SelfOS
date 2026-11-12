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

import copy
from selfos.knowledge.scopes import normalize_scope

def record_version(category, record):
    record=copy.deepcopy(record)
    scoped=category in ('preferences','personal_facts') or record.get('original_category') in ('preferences','personal_facts')
    if scoped:normalize_scope(record)
    fields=[category,record.get('project_id'),record.get('key'),record.get('value'),
            record.get('intent','') if category=='projects' else record.get('text',''),
            record.get('source_ids',[]),record.get('domain')]
    if scoped:fields.extend([record.get('scope_type','unknown'),record.get('scope','unknown')])
    return digest(fields)
def resolve_project_alias(identity, aliases):
    seen=set()
    while identity in aliases:
        if identity in seen:raise ValueError('Cyclic project aliases')
        seen.add(identity)
        identity=aliases[identity]
    return identity
