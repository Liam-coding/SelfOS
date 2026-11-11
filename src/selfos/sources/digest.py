"""sources / digest responsibilities."""
from datetime import date
from collections import defaultdict

def compute_signal_quality(messages: list[dict], raw_line_count: int) -> dict:
    """Compute extraction quality metrics for the digest header.

    Returns a dict with: meaningful_count, raw_count, signal_ratio, label.
    """
    meaningful = len(messages)
    ratio = meaningful / max(raw_line_count, 1)
    if ratio >= 0.4:
        label = "high"
    elif ratio >= 0.15:
        label = "medium"
    else:
        label = "low"
    return {
        "meaningful_count": meaningful,
        "raw_count": raw_line_count,
        "signal_ratio": round(ratio, 2),
        "label": label,
    }


def build_session_digest(messages: list[dict], max_msgs_per_project: int = 40,
                         raw_line_count: int = 0) -> str:
    """
    Group messages by project/cwd, sample up to max_msgs_per_project,
    and render as a structured Markdown digest for the AI to read.
    """
    # Group by (source, cwd or project)
    groups: dict[str, list[dict]] = defaultdict(list)
    for msg in messages:
        key = msg["cwd"] or msg["project"]
        groups[key].append(msg)

    # Sort groups by most recent message
    sorted_groups = sorted(
        groups.items(),
        key=lambda kv: max(m["ts"] for m in kv[1]),
        reverse=True,
    )

    lines = [
        "# SelfOS Session Digest",
        f"Generated: {date.today()}",
        f"Total messages extracted: {len(messages)}",
        f"Projects/contexts: {len(sorted_groups)}",
    ]

    if raw_line_count > 0:
        quality = compute_signal_quality(messages, raw_line_count)
        lines.append(
            f"Signal quality: {quality['label']} "
            f"({quality['meaningful_count']}/{quality['raw_count']} lines = "
            f"{quality['signal_ratio']:.0%})"
        )

    lines += [
        "",
        "---",
        "",
        "## Instructions for AI agent",
        "",
        "Read all sections below. For each context, infer:",
        "- What the user was working on (→ `02_Work/` or `03_Research/`)",
        "- What skills and tools they used (→ `01_Career/`)",
        "- What goals or priorities they expressed (→ `NOW.md`, `GOALS.md`)",
        "- What decisions they made (→ `DECISIONS.md`)",
        "- What they were learning (→ `05_Life/`)",
        "",
        "Then write one staging file per vault module with your findings.",
        "Label all inferences as `[ai-inference]`. Only write what is clearly supported by the text.",
        "",
        "---",
        "",
    ]

    for cwd, msgs in sorted_groups:
        msgs_sorted = sorted(msgs, key=lambda m: m["ts"])
        # Sample: take first 5, last 5, and evenly spaced from the middle
        sampled = _sample_messages(msgs_sorted, max_msgs_per_project)

        latest_ts = max(m["ts"] for m in msgs_sorted)
        source_tags = sorted({m["source"] for m in msgs_sorted})

        lines.append(f"## Context: `{cwd}`")
        lines.append(f"Source: {', '.join(source_tags)} | "
                     f"Messages: {len(msgs_sorted)} | "
                     f"Last active: {latest_ts.strftime('%Y-%m-%d')}")
        lines.append("")

        for msg in sampled:
            ts_str = msg["ts"].strftime("%Y-%m-%d %H:%M")
            lines.append(f"[{ts_str}] {msg['text']}")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _sample_messages(msgs: list[dict], n: int) -> list[dict]:
    """Take a representative sample: head + tail + evenly spaced middle."""
    if len(msgs) <= n:
        return msgs
    head = msgs[:5]
    tail = msgs[-5:]
    middle_count = n - 10
    if middle_count <= 0:
        return head + tail
    middle_pool = msgs[5:-5]
    step = max(1, len(middle_pool) // middle_count)
    middle = middle_pool[::step][:middle_count]
    return head + middle + tail
