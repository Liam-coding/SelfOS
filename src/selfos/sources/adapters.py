"""Fresh evidence resolution through permitted, semantically matching copies."""
import copy
from pathlib import Path

from selfos.sources.documents import SourceUnavailable
from selfos.sources.selection import validate_selection, allowed_database, project_allowed
from selfos.sources.opencode_database import resolve_database
from selfos.sources.opencode_records import opencode_metadata
from selfos.storage.opencode_exports import resolve_export


def verify_source(vault, source, selection):
    if source.get('source') != 'opencode':
        return copy.deepcopy(source)
    metadata = opencode_metadata(source)
    selection = validate_selection({key: value for key, value in selection.items() if key != '_vault'})
    copies, matched = [], None
    for locator in metadata['source_locators']:
        path = Path(locator['path']).resolve()
        if any(path.is_relative_to(Path(rule)) for rule in selection['exclusions'] + selection.get('privacy_exclusions', [])):
            continue
        if not project_allowed(source.get('cwd'), selection):
            continue
        try:
            if locator['kind'] == 'database':
                if not allowed_database(path, selection):
                    continue
                resolved = resolve_database(locator, selection)
            else:
                originals = (Path(vault).resolve() / '.knowledge_uploads/originals').resolve()
                if not path.is_relative_to(originals):
                    continue
                resolved = resolve_export(vault, locator)
            semantic = ('id', 'timestamp', 'role', 'source', 'project_id', 'session_id', 'provenance',
                        'cwd', 'native_project_id', 'native_session_id', 'native_message_id')
            if any(resolved.get(key) != source.get(key) for key in semantic):
                continue
            if 'text' in source and (not isinstance(source['text'], str) or not source['text']
                                      or source['text'] not in resolved['text']):
                continue
            matched = matched or resolved
            copies.append(copy.deepcopy(locator))
        except (ValueError, OSError):
            continue
    if matched is None:
        raise SourceUnavailable('source_changed', 'No permitted unchanged OpenCode source copy is available')
    return {**matched, 'source_locator': copies[0], 'source_locators': copies, 'path': copies[0]['path']}
