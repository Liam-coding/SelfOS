"""Task-relevant vault projection and chat model transport."""
import json
import re
from urllib.request import Request

_CONTEXT_FILES = [
    "PROFILE.md",
    "NOW.md",
    "GOALS.md",
    "DECISIONS.md",
]

def load_vault_context(vault) -> str:
    from selfos.sources.selection import load_sources
    from selfos.app.privacy import model_state
    selection = load_sources(vault)
    restricted = bool(selection['exclusions'] or selection.get('privacy_exclusions'))
    parts = []

    # Current scores — most important context for the chat
    scores_file = vault / "SCORES.md"
    if scores_file.exists() and not restricted:
        text = scores_file.read_text(encoding="utf-8").strip()
        if text:
            parts.append(f"## Current Scores\n{text}")

    for name in _CONTEXT_FILES:
        p = vault / name
        if p.exists() and not restricted:
            text = p.read_text(encoding="utf-8").strip()
            if text:
                parts.append(f"## {name}\n{text}")

    # Latest digest
    inbox = vault / "90_Inbox"
    if inbox.exists() and not restricted:
        digests = sorted(inbox.glob("*-sessions-digest.md"), reverse=True)
        if digests:
            text = digests[0].read_text(encoding="utf-8").strip()
            if text:
                parts.append(f"## Latest Session Digest ({digests[0].name})\n{text[:4000]}")

    state_path = vault / ".knowledge_pipeline.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        generated_lessons=state.get('lessons',[])
        from selfos.knowledge.corrections import apply_corrections
        from selfos.storage.corrections import load_corrections
        state=apply_corrections(state,load_corrections(vault))
        if (vault / '.knowledge_sources.json').exists(): state=model_state(state,selection,vault)
        for category in ('personal_facts', 'preferences'):
            records = [{k: r.get(k) for k in ('text', 'domain', 'conflict', 'observed_at','kind','manual_correction')}
                       for r in state.get(category, [])]
            if records:
                parts.append('## ' + category + '\n' + json.dumps(records, ensure_ascii=False))
        cards = sorted(state.get("cards", {}).values(), key=lambda c: c.get("updated_at", ""), reverse=True)
        for card in cards[:20]:
            current = {k: card.get(k) for k in ("title", "intent", "status", "updated_at", "verified")}
            for field in ("blockers", "next_steps", "decisions"):
                limit = 2000 if field == "next_steps" else 400
                current[field] = [str(v)[:limit] for v in card.get(field, [])[-8:]]
            parts.append("## Current project state\n" + json.dumps(current, ensure_ascii=False))
    elif not restricted:
        cards = sorted((vault / "02_Work/projects").glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        for card in cards[:20]:
            parts.append("## Project summary\n" + card.read_text(encoding="utf-8")[:4000])
    lessons = vault / "05_Life/lessons.md"
    if state_path.exists():
        retained=[{k:r.get(k) for k in ('text','domain','kind','manual_correction','conflict')} for r in state.get('lessons',[])]
        if retained:parts.append('## Reusable lessons'+chr(10)+json.dumps(retained,ensure_ascii=False))
        if lessons.exists() and not restricted:
            notes=lessons.read_text(encoding='utf-8')
            notes=re.sub(r'<!-- selfos-managed-lessons -->.*?<!-- /selfos-managed-lessons -->','',notes,flags=re.S)
            for lesson in generated_lessons:
                block='- ['+lesson.get('kind','inference')+'] '+lesson['text']+'\n  Source: '+', '.join(lesson.get('source_ids',[]))
                notes=notes.replace(block,'')
            if notes.strip():parts.append('## Personal lesson notes\n'+notes.strip()[-8000:])
    elif lessons.exists() and not restricted:
        parts.append("## Reusable lessons\n" + lessons.read_text(encoding="utf-8")[-8000:])
    return "\n\n---\n\n".join(parts)

SYSTEM_PROMPT = """You are a warm, personal AI companion embedded in SelfOS. You know the user well from their vault — their life, work, research, and goals.

Start every conversation like a friend catching up: ask how they're feeling, mention something general about life or energy levels, or just be present. Don't lead with scores or work analysis unless they bring it up first.

When the user wants to go deeper on scores or a specific dimension, you can explain what the scores mean, identify what needs attention, and give concrete suggestions. But always follow their lead — start human, not analytical.

STRICT OUTPUT RULES — no exceptions:
- Plain text only. Zero markdown. No asterisks, no bold, no italics, no hyphens as bullets, no headers, no backticks.
- Short and direct. Two to four sentences normally.
- Conversational, like a friend who knows you well.
- Only reference what is actually in the vault data. If a field is empty, say so briefly and move on.
- Match the user's language (Chinese or English).

Vault context:
{context}"""

def call_model(messages: list[dict], api_key: str, base_url: str, root, context: str) -> str:
    system = SYSTEM_PROMPT.format(context=context)

    payload = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 1024,
        "system": system,
        "messages": messages,
    }).encode()

    req = Request(
        f"{base_url}/v1/messages",
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with __import__('selfos.providers.client', fromlist=['*']).request_opener(root)(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["content"][0]["text"]
