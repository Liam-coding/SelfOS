import re

def normalize_scope(record, session=None):
    """Keep legacy declared scopes; missing applicability remains unknown."""
    scope = record.get('scope')
    declared_type = record.get('scope_type')
    if scope is None:
        kind, identity = 'unknown', 'unknown'
    elif isinstance(scope, dict):
        if set(scope) != {'type', 'id'}:
            raise ValueError('Invalid preference scope fields')
        kind, identity = scope['type'], scope['id']
        if kind in ('global', 'unknown'):
            if identity != '':
                raise ValueError('Global/unknown scope must have an empty id')
            identity = kind
    elif isinstance(scope, str):
        identity = scope
        kind = declared_type or (scope if scope in ('global', 'unknown') else 'activity')
    else:
        raise ValueError('Invalid preference scope')
    if kind not in ('global', 'activity', 'project', 'unknown'):
        raise ValueError('Unsupported preference scope type')
    if declared_type is not None and declared_type != kind:
        raise ValueError('Conflicting preference scope type')
    if not isinstance(identity, str) or not identity or len(identity)>2000 or any(ord(c)<32 for c in identity):
        raise ValueError('Invalid preference scope id')
    if kind!='project' and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}', identity):
        raise ValueError('Invalid preference scope id')
    if kind in ('global', 'unknown') and identity != kind:
        raise ValueError('Invalid global/unknown preference scope id')
    if kind == 'project' and session is not None:
        project = session.get('project_id')
        if identity == 'current-project' and isinstance(project, str) and project:
            identity = project
        elif identity != project:
            raise ValueError('Project scope does not match the source session')
    record['scope_type'] = kind
    record['scope'] = identity.casefold() if kind == 'activity' else identity
    return record
