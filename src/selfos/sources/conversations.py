"""sources / conversations responsibilities."""
import hashlib
import json
import os
from pathlib import Path
from selfos.sources.text import _is_meaningful
from selfos.sources.text import _text_from_content
from selfos.sources.text import redact

def local_roots():
    home = Path.home()
    codex = Path(os.environ.get('CODEX_HOME', str(home / '.codex')))
    claude = Path(os.environ.get('CLAUDE_CONFIG_DIR', str(home / '.claude')))
    roots = [claude / 'projects', codex / 'sessions', codex / 'archived_sessions']
    imports = codex / 'vendor_imports'
    if imports.exists():
        roots.extend(imports.glob('*/archive/.claude/projects'))
        roots.extend(imports.glob('*/session-updates'))
    return roots


def _hash(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def extract_conversations(roots, cancel=lambda: False):
    """Read conversational text only; deduplicate copied session records."""
    found = {}
    paths = sorted({p.resolve() for root in roots if root.exists()
                    for p in ([root] if root.is_file() and root.suffix.lower()=='.jsonl' else root.rglob('*.jsonl'))})
    for path in paths:
        if cancel():
            break
        cwd = ''
        session_id = path.stem
        try:
            with path.open(encoding='utf-8', errors='replace') as stream:
                for line in stream:
                    if cancel():
                        break
                    try:
                        obj = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    if not isinstance(obj, dict):
                        continue
                    payload = obj.get('payload', {})
                    if not isinstance(payload, dict):
                        payload = {}
                    if obj.get('type') == 'session_meta':
                        cwd = payload.get('cwd', '')
                        session_id = payload.get('id') or session_id
                        continue
                    cwd = obj.get('cwd', cwd) or ''
                    session_id = obj.get('sessionId') or session_id
                    if obj.get('type') in ('user', 'assistant'):
                        role, source = obj['type'], 'claude'
                        message = obj.get('message', {})
                        if not isinstance(message, dict):
                            continue
                        content = message.get('content', '')
                    elif obj.get('type') == 'response_item' and payload.get('type') == 'message':
                        if payload.get('channel') == 'analysis':
                            continue
                        role, source = payload.get('role'), 'codex'
                        content = payload.get('content', [])
                    else:
                        continue
                    if role not in ('user', 'assistant'):
                        continue
                    if isinstance(content, list):
                        content = [block for block in content if isinstance(block, dict)
                                   and block.get('type') in ('text', 'input_text', 'output_text')]
                    text = redact(_text_from_content(content)).strip()
                    if not text or (role == 'user' and not _is_meaningful(text)):
                        continue
                    if any(marker in text for marker in ('<environment_context>', '<INSTRUCTIONS>',
                                                         '<system-reminder>', '<task-notification>')):
                        continue
                    timestamp = str(obj.get('timestamp', ''))
                    identity = _hash(json.dumps([source, role, timestamp, text], ensure_ascii=False))
                    found.setdefault(identity, {
                        'id': identity, 'role': role, 'source': source,
                        'timestamp': timestamp, 'text': text, 'path': str(path),
                        'project': redact(Path(cwd).name if cwd else path.parent.name),
                        'project_id': cwd.replace(chr(92), '/').rstrip('/') if cwd else str(path.parent),
                        'session_id': session_id,
                    })
        except OSError:
            continue
    return sorted(found.values(), key=lambda item: (item['timestamp'], item['id']))


def build_batches(messages, max_chars=12000):
    if max_chars <= 0:
        raise ValueError('max_chars must be positive')
    batches, batch, size = [], [], 0
    for message in messages:
        text = message['text']
        for offset in range(0, len(text), max_chars):
            piece = dict(message, text=text[offset:offset + max_chars])
            piece['fragment_id'] = _hash(message['id'] + ':' + str(offset) + ':' + piece['text'])
            if batch and size + len(piece['text']) > max_chars:
                batches.append(batch)
                batch, size = [], 0
            batch.append(piece)
            size += len(piece['text'])
    if batch:
        batches.append(batch)
    return batches
