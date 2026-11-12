"""Read-only chronology of canonical project observations and their provenance."""
from datetime import datetime, timezone
from selfos.knowledge.identity import digest
from selfos.sources.text import redact


def _date(value):
    if not isinstance(value, str) or not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if len(value) == 10:
            return parsed.date().isoformat()
        if parsed.tzinfo is None:
            return ""  # A timezone-free timestamp is ambiguous.
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError):
        return ""


def _texts(value):
    return [redact(text) for text in value if isinstance(text, str)] if isinstance(value, list) else []


def _list(value):
    return value if isinstance(value, list) else []


def project_timeline(state, project_id):
    """Project canonical data without assigning inferred event dates or lifecycle changes."""
    aliases = state.get("project_aliases", {})
    def canonical(identity):
        visited = set()
        while isinstance(aliases, dict) and identity in aliases and identity not in visited:
            visited.add(identity)
            identity = aliases[identity]
        return identity
    project_id = canonical(project_id)
    card = state.get("cards", {}).get(project_id)
    if not isinstance(card, dict):
        raise KeyError("Project not found")
    sources = state.get("sources", {})
    entries = {}

    def add(record, category, text, scope):
        if not isinstance(text, str) or not text.strip():
            return
        ids = sorted(set(identity for identity in _list(record.get("source_ids")) if isinstance(identity, str)))
        scope = record.get("source_scope", scope)
        observed = "" if scope == "project_context" else _date(record.get("observed_at") or record.get("updated_at"))
        times = sorted(set(date for identity in ids
            if isinstance(source := sources.get(identity), dict)
            and (date := _date(source.get("timestamp")))))
        event = _date(record.get("event_time"))
        imported = _date(record.get("imported_at"))
        # Context timestamps describe references, not when a legacy observation occurred.
        order_time = event or observed or (times[0] if times and scope != "project_context" else "")
        basis = "event" if event else "observation" if observed else "source" if order_time else "unknown"
        entry = dict(type=category, text=redact(text), status=record.get("status", "") if category == "progress" else "",
            blockers=_texts(record.get("blockers", [])) if category == "progress" else [],
            next_steps=_texts(record.get("next_steps", [])) if category == "progress" else [],
            event_time=event, observed_at=observed, source_times=times, imported_at=imported,
            order_time=order_time, ordering_basis=basis, source_ids=ids, source_scope=scope,
            kind="inference", verified=False,
            superseded=record.get("superseded") is True,
            domain=redact(str(record.get("domain", card.get("domain", "work")))))
        identity = digest([project_id, entry])
        entry["id"] = identity
        entries[identity] = entry

    def snapshot(record, scope, include_decisions=True):
        add(record, "goals", record.get("intent", ""), scope)
        for decision in _list(record.get("decisions")) if include_decisions else []:
            add(record, "decisions", decision, scope)
        if record.get("status") in ("in_progress", "blocked", "paused", "completed", "reported_complete"):
            add(record, "progress", record["status"], scope)
        for blocker in record.get("blockers", []) if isinstance(record.get("blockers", []), list) else []:
            add(record, "blockers", blocker, scope)

    summaries = state.get("summaries", {})
    found_summary = False
    for summary in summaries.values() if isinstance(summaries, dict) else []:
        record = summary.get("project") if isinstance(summary, dict) else None
        if isinstance(record, dict) and canonical(record.get("project_id")) == project_id:
            snapshot(record, "session_context")
            found_summary = True
    for record in _list(card.get("state_inputs", card.get("state_records", []))):
        if isinstance(record, dict):
            snapshot(record, "project_context")
    lineage = card.get("decision_records", [])
    for record in lineage if isinstance(lineage, list) else []:
        if isinstance(record, dict):
            text = record.get('text', '')
            if not isinstance(text, str) or not text.strip():
                continue
            domain = redact(str(record.get('domain', card.get('domain', 'work'))))
            covered = {identity for entry in entries.values() if entry['type'] == 'decisions'
                       and entry['text'] == redact(text) and entry['domain'] == domain
                       for identity in entry['source_ids']}
            ids = [identity for identity in _list(record.get('source_ids')) if isinstance(identity, str)]
            remaining = [identity for identity in ids if identity not in covered]
            if remaining or (not ids and not any(entry['type'] == 'decisions' and entry['text'] == redact(text) for entry in entries.values())):
                residual = {**record, 'source_ids': remaining}
                if remaining != ids:
                    # Aggregate dates do not identify the remaining supporting episode.
                    residual.pop('observed_at', None)
                    residual.pop('updated_at', None)
                    residual['source_scope'] = 'project_context'
                add(residual, "decisions", text, "project_context")
    for text in _list(card.get("decision_history", card.get("decisions", []))):
        if isinstance(text, str) and not any(entry['type'] == 'decisions' and entry['text'] == redact(text) for entry in entries.values()):
            add(card, "decisions", text, "project_context")
    if not found_summary:
        snapshot(card, "project_context", include_decisions=False)
    current = dict(title=redact(str(card.get("title", ""))), intent=redact(str(card.get("intent", ""))),
        status=card.get("status", "unknown"), decisions=_texts(card.get("decisions", [])),
        blockers=_texts(card.get("blockers", [])), next_steps=_texts(card.get("next_steps", [])),
        observed_at=_date(card.get("updated_at")), verified=bool(card.get("verified")))
    return {"current": current, "entries": sorted(entries.values(),
        key=lambda entry: (not bool(entry["order_time"]), entry["order_time"], entry["id"]))}
