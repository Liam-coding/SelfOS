"""Local, bounded previews that require an explicit action before processing."""
import hashlib
import uuid
import re
from collections import defaultdict
from pathlib import Path

from selfos.knowledge.identity import digest
from selfos.knowledge.settings import limits, policy_hash
from selfos.storage.settings import load_settings
from selfos.sources.compaction import prepare_sessions
from selfos.sources.conversations import extract_conversations
from selfos.sources.selection import load_sources, select_files, allowed_source
from selfos.storage.onboarding import read_metadata, write_metadata

TIERS = {"sample": (2, 2, 20, 12), "more": (4, 4, 40, 24)}
PREVIEW_BYTES = 2 * 1024 * 1024


def _file_identity(path):
    before = path.stat()
    if before.st_size > 8 * 1024 * 1024:
        raise ValueError("Preview source changed or exceeds file limit")
    with path.open("rb") as stream:
        data = stream.read(8 * 1024 * 1024 + 1)
    after = path.stat()
    if len(data) != before.st_size or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Preview source changed while reading")
    return {"path": str(path.resolve()), "size": after.st_size, "mtime_ns": after.st_mtime_ns,
            "sha256": hashlib.sha256(data).hexdigest()}


def _sessions(paths, settings, tier):
    _, parts_limit, messages_limit, _ = TIERS[tier]
    messages = extract_conversations(paths)
    groups = defaultdict(list)
    for message in messages:
        groups[(message["project_id"], message["session_id"])].append(message)
    selected = [message for group in groups.values() for message in group[-messages_limit:]]
    sessions = prepare_sessions(selected, max_chars=limits(settings)["session_chars"])
    clipped = len(selected) < len(messages) or len(sessions) > parts_limit
    sessions = sessions[:parts_limit]
    for session in sessions:
        session["partial_input"] = True
        session["fingerprint"] = digest(["onboarding-partial-v1", session["fingerprint"]])
    return sessions, clipped


def build_preview(vault, tier="sample"):
    if tier not in TIERS:
        raise ValueError("Unsupported preview tier")
    files_limit, _, _, budget_limit = TIERS[tier]
    selection = load_sources(vault)
    settings = load_settings(vault)
    paths, warnings = select_files(selection, file_limit=files_limit)
    identities = [_file_identity(path) for path in paths]
    sessions, clipped = _sessions(paths, settings, tier)
    if identities != [_file_identity(path) for path in paths]:
        raise ValueError("Preview sources changed while reading")
    preview_id = uuid.uuid4().hex
    preview = {"version": 1, "id": preview_id, "tier": tier, "files": identities,
               "sessions": sessions, "clipped": clipped or bool(warnings), "warnings": warnings,
               "budget_limit": budget_limit, "selection_hash": digest(selection),
               "policy_hash": policy_hash(settings),
               "message_ids": sorted({m["id"] for s in sessions for m in s["messages"]})}
    write_metadata(vault, f".knowledge_onboarding/previews/{preview_id}.json", preview, PREVIEW_BYTES)
    write_metadata(vault, f".knowledge_onboarding/budgets/{preview_id}.json",
                   {"version": 1, "used": 0, "limit": budget_limit})
    return preview


def resolve_preview(vault, preview_id):
    preview = read_metadata(vault, f".knowledge_onboarding/previews/{preview_id}.json", max_bytes=PREVIEW_BYTES)
    if not isinstance(preview, dict) or preview.get("version") != 1 or preview.get("id") != preview_id or preview.get("tier") not in TIERS:
        raise ValueError("Invalid or missing preview")
    selection = load_sources(vault)
    if preview.get("selection_hash") != digest(selection) or preview.get("policy_hash") != policy_hash(load_settings(vault)):
        raise ValueError("Preview settings changed; create a new preview")
    files = preview.get("files")
    if not isinstance(files, list) or len(files) > TIERS[preview["tier"]][0]:
        raise ValueError("Invalid preview files")
    for identity in files:
        path = Path(identity["path"])
        if not allowed_source(path, selection) or not path.is_file() or identity != _file_identity(path):
            raise ValueError("Preview source changed; create a new preview")
    sessions, _ = _sessions([Path(item["path"]) for item in files], load_settings(vault), preview["tier"])
    if (preview.get("sessions") != sessions or preview.get("budget_limit") != TIERS[preview["tier"]][3]
            or preview.get("message_ids") != sorted({m["id"] for s in sessions for m in s["messages"]})
            or files != [_file_identity(Path(item["path"])) for item in files]):
        raise ValueError("Invalid or changed preview material; create a new preview")
    return preview


def _progress(vault):
    value = read_metadata(vault, '.knowledge_onboarding.json',
                          {'version': 1, 'step': 0, 'status': 'new', 'preview_id': None})
    if (not isinstance(value, dict) or value.get('version') != 1
            or type(value.get('step')) is not int or not 0 <= value['step'] <= 4
            or value.get('status') not in ('new', 'active', 'skipped', 'done')
            or (value.get('preview_id') is not None and (not isinstance(value['preview_id'], str)
                or not re.fullmatch('[a-f0-9]{32}', value['preview_id'])))
            or set(value) - {'version', 'step', 'status', 'preview_id'}):
        raise ValueError('Invalid onboarding progress; preserve metadata and repair it before continuing')
    return value


def onboarding_status(vault, config_root):
    from selfos.sources.selection import discover_sources
    from selfos.providers.settings import public_config
    from selfos.app.knowledge_status import get_status
    from selfos.storage.onboarding import SampleBudget
    progress = _progress(vault)
    selection = load_sources(vault)
    preview = None
    budget = None
    if progress['preview_id']:
        preview = read_metadata(vault, f".knowledge_onboarding/previews/{progress['preview_id']}.json", max_bytes=PREVIEW_BYTES)
        budget = SampleBudget(vault, progress['preview_id']).status()
    from selfos.sources.opencode_discovery import discover_opencode
    native = discover_opencode()
    discovered = {entry['path'] for entry in native}
    native += [dict(entry, source='opencode', available=Path(entry['path']).is_file()) for entry in selection.get('entries', [])
               if entry['kind'] == 'opencode_database' and entry['path'] not in discovered]
    return {'progress': progress, 'sources': selection,
            'availability': discover_sources(defaults=selection['roots']) + native, 'model': public_config(config_root),
            'knowledge': get_status(vault), 'preview': preview, 'budget': budget}


def onboarding_action(vault, config_root, body):
    from selfos.storage.files import _locked
    from selfos.sources.selection import save_sources
    from selfos.storage.onboarding import SampleBudget
    fields = {'save_sources': {'action', 'sources'}, 'save_step': {'action', 'step'},
              'skip': {'action'}, 'resume': {'action'}, 'preview': {'action', 'tier'},
              'new_allowance': {'action', 'preview_id'}, 'start': {'action', 'preview_id'}}
    if not isinstance(body, dict) or body.get('action') not in fields or set(body) - fields[body['action']]:
        raise ValueError('Invalid onboarding action')
    action = body['action']
    if action == 'save_step' and (type(body.get('step')) is not int or not 0 <= body['step'] <= 4):
        raise ValueError('Invalid onboarding step')
    if action in ('start', 'new_allowance'):
        # Reject stale/missing IDs before creating any progress or lock files.
        selected = resolve_preview(vault, body.get('preview_id', ''))
        if action == 'start' and (not selected['sessions'] or SampleBudget(vault, selected['id']).status()['remaining'] == 0):
            raise ValueError('No sample work or request allowance remains; create a new preview')
    if action == 'preview' and body.get('tier', 'sample') not in TIERS:
        raise ValueError('Invalid preview tier')
    progress = _progress(vault)
    with _locked(Path(vault).resolve() / '.knowledge_onboarding' / 'progress'):
        progress = _progress(vault)
        if action == 'save_sources':
            save_sources(vault, body.get('sources'))
            progress.update(preview_id=None, status='active')
        elif action == 'save_step':
            progress.update(step=body['step'], status='active')
        elif action in ('skip', 'resume'):
            progress['status'] = 'skipped' if action == 'skip' else 'active'
        elif action in ('preview', 'new_allowance'):
            preview = build_preview(vault, tier=body.get('tier', 'sample') if action == 'preview' else selected['tier'])
            progress.update(step=3, status='active', preview_id=preview['id'])
        elif action == 'start':
            if progress.get('preview_id') != selected['id']:
                raise ValueError('Preview is no longer current; reopen setup')
            resolve_preview(vault, selected['id'])
            progress.update(step=4, status='active')
        write_metadata(vault, '.knowledge_onboarding.json', progress)
    result = onboarding_status(vault, config_root)
    if action == 'start':
        result['stream_url'] = '/__knowledge_stream__?preview=' + selected['id']
    return result
