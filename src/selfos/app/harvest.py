"""app / harvest responsibilities."""
from selfos.web.rendering.dashboard import STATE_FILE_NAME
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from selfos.sources.readers import extract_claude_messages
from selfos.sources.readers import extract_codex_messages

def load_state(vault: Path) -> dict:
    state_file = vault / STATE_FILE_NAME
    if state_file.exists():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(vault: Path, state: dict) -> None:
    state_file = vault / STATE_FILE_NAME
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


def resolve_since(args_days: int, args_full: bool, state: dict) -> datetime | None:
    """Compute the `since` cutoff from CLI args and persisted state.

    Returns None for full extraction, or a timezone-aware datetime to filter from.
    """
    if args_days > 0:
        return datetime.now(timezone.utc) - timedelta(days=args_days)
    if args_full or "last_run" not in state:
        return None
    return datetime.fromisoformat(state["last_run"])


def run_extraction(vault: Path, since: datetime | None, verbose: bool = True) -> tuple[list[dict], int]:
    """Extract all messages and return (sorted list, total raw user line count)."""
    if verbose:
        print("  Reading Claude Code sessions...", end=" ", flush=True)
    claude_msgs, claude_raw = extract_claude_messages(since)
    if verbose:
        print(f"{len(claude_msgs)} messages")

    if verbose:
        print("  Reading Codex sessions...", end=" ", flush=True)
    codex_msgs, codex_raw = extract_codex_messages(since)
    if verbose:
        print(f"{len(codex_msgs)} messages")

    all_msgs = claude_msgs + codex_msgs
    all_msgs.sort(key=lambda m: m["ts"])
    return all_msgs, claude_raw + codex_raw


def build_stats_report(messages: list[dict]) -> str:
    """Build a per-project statistics table from extracted messages."""
    from collections import defaultdict
    groups: dict[str, list[dict]] = defaultdict(list)
    for msg in messages:
        key = msg["cwd"] or msg["project"]
        groups[key].append(msg)

    sorted_groups = sorted(
        groups.items(),
        key=lambda kv: max(m["ts"] for m in kv[1]),
        reverse=True,
    )

    lines = [
        f"{'Context':<55} {'Msgs':>5}  {'First':>10}  {'Last':>10}  {'Source':<10}",
        "-" * 95,
    ]
    for key, msgs in sorted_groups:
        first = min(m["ts"] for m in msgs).strftime("%Y-%m-%d")
        last = max(m["ts"] for m in msgs).strftime("%Y-%m-%d")
        sources = "/".join(sorted({m["source"] for m in msgs}))
        label = key[-52:] if len(key) > 52 else key
        lines.append(f"{label:<55} {len(msgs):>5}  {first:>10}  {last:>10}  {sources:<10}")

    lines.append("-" * 95)
    lines.append(f"Total: {len(messages)} messages across {len(sorted_groups)} contexts")
    return "\n".join(lines)
