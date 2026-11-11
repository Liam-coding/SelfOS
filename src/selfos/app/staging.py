"""app / staging responsibilities."""
import re
import json
from pathlib import Path
from datetime import date
from urllib.request import Request
from urllib.error import URLError
from selfos.providers.config import _get_api_config

_STAGING_SYSTEM = """You are a vault assistant for SelfOS. Your job is to read a session digest and extract structured updates for each vault module.

Output ONLY a JSON array. Each element is one staging file to write:
{
  "target": "vault/NOW.md",          // canonical file path (relative to project root)
  "type": "now",                     // one of: now, career, work, research, health, learning, goals, decisions
  "content": "---\\ntype: now\\n...\\n---\\n\\n# Now\\n..."  // full file content to write
}

Rules:
- Label every inference with [ai-inference]
- Only write what is clearly supported by the digest text
- Preserve existing confirmed facts from the current vault content provided
- For decisions: append-only — include existing decisions plus any new ones
- For NOW.md: replace with current state, keep confirmed facts, add new [ai-inference] items
- Skip a module entirely if there is nothing new to add
- Output valid JSON only, no markdown fences, no explanation"""


_STAGING_PROMPT = """Here is the session digest:

{digest}

---

Here is the current state of key vault files:

{vault_context}

---

Generate staging updates for these modules (only include modules with new information):
- vault/NOW.md (current priorities, active work)
- vault/GOALS.md (explicit goals stated)
- vault/02_Work/selfos.md (SelfOS project state)
- vault/03_Research/mem_anno.md (MemAnno research state)
- vault/04_Health_Fitness/log.md (health, fitness, training)
- vault/05_Life/learning.md (learning goals, IELTS, courses)

Output a JSON array as specified."""


def _read_vault_file(path: Path, max_chars: int = 1500) -> str:
    if not path.exists():
        return "(file does not exist yet)"
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return text[:max_chars] if len(text) > max_chars else text


def auto_generate_staging(vault: Path, digest_path: Path) -> list[Path]:
    """Call Claude API to generate staging files from the latest digest.
    Returns list of written staging file paths."""
    root = vault.parent
    api_key, base_url = _get_api_config(root)
    if not api_key and __import__('selfos.providers.settings', fromlist=['*']).load_config(root)['provider']=='anthropic':
        print("  [auto-staging] Skipped — ANTHROPIC_API_KEY not set")
        return []

    digest_text = digest_path.read_text(encoding="utf-8", errors="replace")
    # trim digest to avoid token overrun
    if len(digest_text) > 8000:
        digest_text = digest_text[:8000] + "\n...[truncated]"

    vault_context_parts = [
        f"=== vault/NOW.md ===\n{_read_vault_file(vault / 'NOW.md')}",
        f"=== vault/GOALS.md ===\n{_read_vault_file(vault / 'GOALS.md')}",
        f"=== vault/02_Work/selfos.md ===\n{_read_vault_file(vault / '02_Work' / 'selfos.md')}",
        f"=== vault/03_Research/mem_anno.md ===\n{_read_vault_file(vault / '03_Research' / 'mem_anno.md')}",
    ]
    vault_context = "\n\n".join(vault_context_parts)

    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 4096,
        "system": _STAGING_SYSTEM,
        "messages": [{"role": "user", "content": _STAGING_PROMPT.format(
            digest=digest_text,
            vault_context=vault_context,
        )}],
    }).encode()

    try:
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
        with __import__('selfos.providers.client', fromlist=['*']).request_opener(root)(req, timeout=60) as resp:
            data = json.loads(resp.read())
        raw = data["content"][0]["text"].strip()
    except URLError as e:
        print(f"  [auto-staging] API error: {e}")
        return []
    except Exception as e:
        print(f"  [auto-staging] Failed: {e}")
        return []

    try:
        updates = json.loads(raw)
    except json.JSONDecodeError:
        # try to extract JSON array from response
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        if not m:
            print("  [auto-staging] Could not parse AI response as JSON")
            return []
        try:
            updates = json.loads(m.group())
        except json.JSONDecodeError:
            print("  [auto-staging] Could not parse AI response as JSON")
            return []

    staging_dir = vault / "91_Staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    written = []

    for item in updates:
        if not isinstance(item, dict):
            continue
        target = item.get("target", "")
        module_type = item.get("type", "misc")
        content = item.get("content", "")
        if not target or not content:
            continue

        # derive a short name from the target path
        slug = Path(target).stem.replace("_", "-").lower()
        staging_path = staging_dir / f"{today}-auto-{slug}.md"

        # write staging file with frontmatter
        frontmatter = f"---\ntype: {module_type}\nupdated: {today}\nsource: auto-harvest\ntarget: {target}\n---\n\n"
        staging_path.write_text(frontmatter + content, encoding="utf-8")
        written.append(staging_path)

    return written
