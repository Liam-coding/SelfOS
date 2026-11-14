"""sources / compaction responsibilities."""
import copy
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from functools import lru_cache
from selfos.sources.text import redact
from selfos.knowledge.identity import unique





@lru_cache(maxsize=512)
def canonical_project(identity):
    path = Path(identity)
    if not path.is_absolute() or not path.is_dir():
        return identity
    for parent in (path, *path.parents):
        git = parent / ".git"
        if git.is_dir():
            return str(parent).replace(chr(92), "/")
        if git.is_file():
            content = git.read_text(encoding="utf-8").strip()
            if content.startswith("gitdir:"):
                gitdir = (parent / content[7:].strip()).resolve()
                common = gitdir / "commondir"
                if common.exists():
                    directory = (gitdir / common.read_text().strip()).resolve()
                    return str(directory.parent if directory.name == ".git" else directory).replace(chr(92), "/")
            return str(parent).replace(chr(92), "/")
    return identity








def prepare_sessions(messages, max_chars=12000, cancel=lambda: False, aliases=None, audit=None):
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    groups = defaultdict(dict)
    if audit is not None:
        audit.update(input_messages=0, filtered_messages=0, examples=[])
    for raw in messages:
        if cancel():
            break
        m = compact_message(raw)
        if audit is not None:
            audit['input_messages'] += 1
        if m is None:
            if audit is not None:
                from selfos.knowledge.filtering import transient_only
                audit['filtered_messages'] += 1
                if len(audit['examples']) < 10:
                    audit['examples'].append({'source_ids':[raw['id']], 'reason':
                        'transient_content' if transient_only(raw.get('text','')) else 'runtime_content'})
            continue
        project_id = canonical_project(raw.get("project_id") or raw.get("project") or "unknown")
        if aliases:
            project_id = aliases.get(project_id, project_id)
        if m.get('source') != 'opencode':
            m['project_id'] = project_id
        m["session_id"] = raw.get("session_id") or raw.get("path") or "unknown"
        groups[(project_id, m["session_id"])].setdefault(m["id"], m)
    sessions = []
    for (project, session), records in sorted(groups.items()):
        if cancel():
            break
        parts, part = pack_records(sorted(records.values(), key=lambda x: (x.get("timestamp", ""), x["id"])), max_chars)
        if part:
            parts.append(part)
        for index, part in enumerate(parts):
            sessions.append(dict(project_id=project, session_id=session, part=index, messages=part,
                                 fingerprint=part_fingerprint(part)))
    return sessions


def pack_records(messages, max_chars, part=None):
    """Pack already normalized, ordered records without changing existing slice metadata."""
    parts, part = [], list(part or [])
    size = sum(len(message['text']) for message in part)
    for message in messages:
        for offset in range(0, len(message['text']), max_chars):
            piece = {**message, 'text': message['text'][offset:offset + max_chars]}
            if part and size + len(piece['text']) > max_chars:
                parts.append(part)
                part, size = [], 0
            part.append(piece)
            size += len(piece['text'])
    return parts, part


def part_fingerprint(messages):
    transport = {'path', 'source_locator', 'source_locators', 'document_id', 'content_sha256', 'original_filename'}
    return digest([{key: value for key, value in message.items() if key not in transport}
                   if message.get('source') == 'opencode' else message for message in messages])

from selfos.knowledge.filtering import compact_message
from selfos.knowledge.identity import digest
