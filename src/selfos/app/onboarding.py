"""Local, bounded previews that require an explicit action before processing."""
import hashlib
import uuid
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
