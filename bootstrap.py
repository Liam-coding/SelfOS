#!/usr/bin/env python3
"""
SelfOS Bootstrap — Build a self-portrait from your AI conversation history.

Usage:
    python bootstrap.py           # extract all sessions, write to ./vault
    python bootstrap.py --days 30 # last 30 days only

The script reads Claude Code and Codex session files, extracts your messages,
filters sensitive data, and writes a digest to vault/90_Inbox/.

Your AI agent then reads the digest and distributes insights across vault modules.
Nothing is written to canonical vault files without your approval.
"""

import os
import re
import json
import argparse
import subprocess
from pathlib import Path
from datetime import date, datetime, timezone, timedelta
from collections import defaultdict

# ── Sensitive data patterns ───────────────────────────────────────────────────
SENSITIVE_PATTERNS = [
    r"(?i)(password|passwd|pwd)\s*[=:]\s*\S+",
    r"(?i)(secret|token|api[_-]?key|access[_-]?key)\s*[=:]\s*\S+",
    r"(?i)(private[_-]?key|client[_-]?secret)\s*[=:]\s*\S+",
    r"[A-Za-z0-9+/]{40,}={0,2}",
    r"sk-[A-Za-z0-9]{20,}",
    r"ghp_[A-Za-z0-9]{36}",
    r"xox[baprs]-[A-Za-z0-9-]+",
    r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
]
SENSITIVE_RE = [re.compile(p) for p in SENSITIVE_PATTERNS]

def redact(value: str) -> str:
    for r in SENSITIVE_RE:
        value = r.sub("[REDACTED]", value)
    return value

def is_sensitive(value: str) -> bool:
    return any(r.search(value) for r in SENSITIVE_RE)


# ── Message extraction ────────────────────────────────────────────────────────

def _text_from_content(content) -> str:
    """Extract plain text from a message content field (str or list of blocks)."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text") or block.get("input_text") or "")
        return " ".join(p for p in parts if p).strip()
    return ""


def _is_meaningful(text: str) -> bool:
    """Skip noise: one-word acks, system notifications, file paths, loop prompts."""
    text = text.strip()
    if len(text) < 8:
        return False
    if text.lower() in {"ok", "yes", "no", "对", "好", "是", "嗯", "apply", "done"}:
        return False
    # Skip system task-notification XML blocks
    if "<task-notification>" in text or "<task-id>" in text:
        return False
    # Skip messages that are mostly a file path (loop monitoring prompts)
    if re.match(r'^(Check|Read|Run)\s+(eval|progress|the file)', text, re.IGNORECASE):
        return False
    # Skip pure Windows path messages
    if re.match(r'^[A-Za-z]:\\', text) and len(text) < 120:
        return False
    return True


def extract_claude_messages(since: datetime | None = None) -> list[dict]:
    """
    Extract user messages from all Claude Code session files.
    Returns list of {timestamp, project, cwd, text}.
    """
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        return []

    messages = []
    for proj_dir in claude_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        project_name = _decode_claude_project_name(proj_dir.name)

        for session_file in proj_dir.glob("*.jsonl"):
            try:
                with open(session_file, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        obj = json.loads(line)
                        if obj.get("type") != "user":
                            continue
                        ts_str = obj.get("timestamp", "")
                        ts = _parse_ts(ts_str)
                        if since and ts and ts < since:
                            continue
                        content = obj.get("message", {}).get("content", "")
                        text = _text_from_content(content)
                        text = redact(text)
                        if not _is_meaningful(text):
                            continue
                        messages.append({
                            "ts": ts or datetime.min.replace(tzinfo=timezone.utc),
                            "source": "claude",
                            "project": project_name,
                            "cwd": obj.get("cwd", ""),
                            "text": text,
                        })
            except Exception:
                continue

    return messages


def extract_codex_messages(since: datetime | None = None) -> list[dict]:
    """
    Extract user messages from all Codex session files.
    Returns list of {timestamp, project, cwd, text}.
    """
    sessions_dir = Path.home() / ".codex" / "sessions"
    if not sessions_dir.exists():
        return []

    messages = []
    for session_file in sessions_dir.rglob("*.jsonl"):
        cwd = ""
        try:
            with open(session_file, encoding="utf-8", errors="replace") as f:
                for line in f:
                    obj = json.loads(line)

                    # grab cwd from session_meta
                    if obj.get("type") == "session_meta":
                        cwd = obj.get("payload", {}).get("cwd", "")
                        continue

                    if obj.get("type") != "response_item":
                        continue

                    payload = obj.get("payload", {})
                    if payload.get("role") != "user":
                        continue

                    ts_str = obj.get("timestamp", "")
                    ts = _parse_ts(ts_str)
                    if since and ts and ts < since:
                        continue

                    content = payload.get("content", [])
                    text = _text_from_content(content)
                    text = redact(text)
                    if not _is_meaningful(text):
                        continue

                    project = Path(cwd).name if cwd else session_file.stem[:20]
                    messages.append({
                        "ts": ts or datetime.min.replace(tzinfo=timezone.utc),
                        "source": "codex",
                        "project": project,
                        "cwd": cwd,
                        "text": text,
                    })
        except Exception:
            continue

    return messages


def _decode_claude_project_name(dir_name: str) -> str:
    """Extract the last path segment from an encoded Claude project dir name.

    Windows: C--Users-foo-myproject  (drive letter + -- prefix)
    macOS:   -Users-foo-myproject    (leading - for root /)
    """
    # Windows: starts with drive letter(s) + --
    m = re.match(r'^[A-Za-z]{1,2}--(.+)$', dir_name)
    if m:
        parts = [p for p in m.group(1).split("-") if p]
        return parts[-1] if parts else dir_name
    # macOS/Linux: starts with - (encoding of leading /)
    if dir_name.startswith("-"):
        parts = [p for p in dir_name.split("-") if p]
        return parts[-1] if parts else dir_name
    return dir_name


def _parse_ts(ts_str: str) -> datetime | None:
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except Exception:
        return None


# ── Group and format digest ───────────────────────────────────────────────────

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


# ── Workspace discovery (kept from previous version) ─────────────────────────

def _decode_claude_project_path(dir_name: str) -> Path | None:
    """Decode a Claude Code project directory name back to a filesystem path.

    Windows encoding: C--Users-foo-bar  →  C:\\Users\\foo\\bar
    macOS encoding:   -Users-foo-bar    →  /Users/foo/bar
    """
    # Windows: drive letter(s) + -- + path segments separated by -
    m = re.match(r'^([A-Za-z]{1,2})--(.+)$', dir_name)
    if m:
        drive = m.group(1).upper() + ":"
        rest = m.group(2).replace("-", os.sep)
        p = Path(drive + os.sep + rest)
        return p if p.exists() else None

    # macOS/Linux: leading - encodes the root /
    if dir_name.startswith("-"):
        rest = dir_name[1:].replace("-", "/")
        p = Path("/" + rest)
        return p if p.exists() else None

    return None


def discover_claude_workspaces() -> list[Path]:
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        return []
    workspaces = []
    for entry in claude_dir.iterdir():
        if not entry.is_dir():
            continue
        p = _decode_claude_project_path(entry.name)
        if p and p.is_dir():
            workspaces.append(p)
    return sorted(set(workspaces))


def discover_codex_workspaces() -> list[Path]:
    workspaces = set()
    env_ws = os.environ.get("OPENAI_CODEX_WORKSPACE")
    if env_ws:
        p = Path(env_ws)
        if p.is_dir():
            workspaces.add(p)
    codex_dir = Path.home() / ".codex"
    sessions_dir = codex_dir / "sessions"
    for session_file in sessions_dir.rglob("*.jsonl"):
        try:
            with open(session_file, encoding="utf-8", errors="replace") as f:
                for line in f:
                    obj = json.loads(line)
                    if obj.get("type") == "session_meta":
                        cwd = obj.get("payload", {}).get("cwd", "")
                        if cwd:
                            p = Path(cwd)
                            if p.is_dir():
                                workspaces.add(p)
                        break
        except Exception:
            continue
    return sorted(workspaces)


def discover_all_workspaces() -> dict:
    claude_ws = discover_claude_workspaces()
    codex_ws = discover_codex_workspaces()
    all_paths = set(claude_ws) | set(codex_ws)
    return {"claude": claude_ws, "codex": codex_ws, "all": sorted(all_paths)}


def build_discovery_report(discovered: dict) -> str:
    claude_lines = "\n".join(f"  - {p}" for p in discovered["claude"]) or "  (none found)"
    codex_lines = "\n".join(f"  - {p}" for p in discovered["codex"]) or "  (none found)"
    return f"""---
type: discovery-report
updated: {date.today()}
source: bootstrap-discover-{date.today()}
---

# Workspace Discovery Report

## Claude Code workspaces
{claude_lines}

## Codex workspaces
{codex_lines}

## All unique workspaces ({len(discovered['all'])} total)
{chr(10).join(f'  - {p}' for p in discovered['all']) or '  (none found)'}

## Next step
    python bootstrap.py --sessions --vault ./vault
"""


# ── Code workspace scan (kept from previous version) ─────────────────────────

def get_git_info(workspace: Path) -> dict:
    info = {}
    try:
        name = subprocess.check_output(["git", "config", "user.name"], cwd=workspace, text=True).strip()
        if name and not is_sensitive(name):
            info["name"] = name
        email = subprocess.check_output(["git", "config", "user.email"], cwd=workspace, text=True).strip()
        if email and not is_sensitive(email):
            info["email"] = email
        remotes = subprocess.check_output(["git", "remote", "-v"], cwd=workspace, text=True).strip()
        repos = re.findall(r"github\.com[:/]([^/\s]+/[^\s.]+)", remotes)
        if repos:
            info["github_repos"] = list(set(repos))
    except Exception:
        pass
    return info


def detect_stack(workspace: Path) -> list:
    stack = []
    indicators = {
        "Python": ["*.py", "requirements.txt", "pyproject.toml", "setup.py"],
        "Java": ["*.java", "pom.xml", "build.gradle"],
        "JavaScript/TypeScript": ["package.json", "*.ts", "*.tsx"],
        "Rust": ["Cargo.toml"],
        "Go": ["go.mod"],
        "Docker": ["Dockerfile", "docker-compose.yml"],
        "Kubernetes": ["*.yaml"],
    }
    for tech, patterns in indicators.items():
        for pattern in patterns:
            if list(workspace.glob(pattern)) or list(workspace.rglob(pattern)):
                stack.append(tech)
                break
    return stack


def extract_project_description(workspace: Path) -> str:
    for name in ["README.md", "README.rst", "README.txt"]:
        readme = workspace / name
        if readme.exists():
            content = readme.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
            paragraphs, current = [], []
            for line in lines:
                if line.strip():
                    current.append(line.strip())
                elif current:
                    paragraphs.append(" ".join(current))
                    current = []
            for p in paragraphs:
                if not p.startswith("#"):
                    return redact(p[:300])
    return ""


def scan_workspace(workspace: Path, vault: Path) -> None:
    staging = vault / "91_Staging"
    staging.mkdir(parents=True, exist_ok=True)
    prefix = f"{date.today()}-{workspace.name}"
    print(f"\n{'='*60}\nScanning: {workspace}\n{'='*60}")
    git_info = get_git_info(workspace)
    stack = detect_stack(workspace)
    description = extract_project_description(workspace)
    print(f"  Git user : {git_info.get('name', 'not found')}")
    print(f"  Stack    : {', '.join(stack) if stack else 'none'}")

    profile_path = staging / f"{prefix}-profile.md"
    profile_path.write_text(_build_profile_draft(git_info, stack, description), encoding="utf-8")
    print(f"  Profile draft  : {profile_path.relative_to(vault)}")

    project_path = staging / f"{prefix}-project.md"
    project_path.write_text(_build_project_draft(workspace, stack, description), encoding="utf-8")
    print(f"  Project draft  : {project_path.relative_to(vault)}")


def _build_profile_draft(git_info, stack, description):
    name = git_info.get("name", "[Your Name]")
    repos = git_info.get("github_repos", [])
    github = f"https://github.com/{repos[0].split('/')[0]}" if repos else "[github.com/username]"
    stack_str = ", ".join(stack) if stack else "[fill in your stack]"
    return f"""---
type: profile
updated: {date.today()}
source: bootstrap-{date.today()}
---

# Profile

## Identity
- Full name: {name}
- Preferred name: [fill in]
- Birth year: [fill in]
- Location: [fill in]

## Current Role
- Title: [fill in]
- Company: [fill in]

## Technical Strengths
- {stack_str}

## GitHub
- {github}

## Notes from bootstrap scan
{('- Found repos: ' + ', '.join(repos)) if repos else '- No repos detected'}
{('- Project description: ' + description) if description else ''}
"""


def _build_project_draft(workspace, stack, description):
    return f"""---
type: project-context
updated: {date.today()}
source: bootstrap-{date.today()}
---

# Project Context

## Active Projects

### {workspace.name}
- **Status**: in progress
- **Stack**: {', '.join(stack) if stack else '[fill in]'}
- **Description**: {description if description else '[fill in]'}
- **Goal**: [what done looks like]
- **Next action**: [concrete next step]

## Notes
- Scanned from: {workspace}
"""


# ── Skill installation ────────────────────────────────────────────────────────

def install_skill() -> bool:
    """Copy .claude/skills/digest to ~/.claude/skills/. Returns True if installed."""
    src = Path(__file__).parent / ".claude" / "skills" / "digest"
    dst = Path.home() / ".claude" / "skills" / "digest"
    if not src.exists():
        return False
    if dst.exists():
        return True  # already installed
    import shutil
    shutil.copytree(src, dst)
    return True


def cleanup_old_digests(inbox: Path, keep: int = 7) -> int:
    """Delete old digest files, keeping the most recent `keep` files. Returns count deleted."""
    digests = sorted(inbox.glob("*-sessions-digest.md"))
    to_delete = digests[:-keep] if len(digests) > keep else []
    for f in to_delete:
        f.unlink()
    return len(to_delete)


VAULT_DIRS = [
    "90_Inbox",
    "91_Staging",
    "01_Career",
    "02_Work",
    "03_Research",
    "04_Health_Fitness",
    "05_Life",
    "06_Reviews",
    "98_Archive",
    "99_Templates",
]

VAULT_FILES = ["PROFILE.md", "NOW.md", "GOALS.md", "DECISIONS.md", "CLAUDE.md"]


def ensure_vault_structure(vault: Path) -> list[str]:
    """Create missing vault dirs and files. Returns list of items created."""
    created = []
    for d in VAULT_DIRS:
        p = vault / d
        if not p.exists():
            p.mkdir(parents=True)
            created.append(f"  + {d}/")

    templates_src = Path(__file__).parent / "vault"
    for fname in VAULT_FILES:
        dest = vault / fname
        if not dest.exists():
            src = templates_src / fname
            if src.exists():
                import shutil
                shutil.copy2(src, dest)
            else:
                dest.write_text(f"# {fname.replace('.md', '')}\n\n", encoding="utf-8")
            created.append(f"  + {fname}")

    return created


# ── Main ──────────────────────────────────────────────────────────────────────

STATE_FILE_NAME = ".bootstrap_state.json"


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


def run_extraction(vault: Path, since: datetime | None, verbose: bool = True) -> list[dict]:
    """Extract all messages and return sorted list. Side-effect: prints progress."""
    if verbose:
        print("  Reading Claude Code sessions...", end=" ", flush=True)
    claude_msgs = extract_claude_messages(since)
    if verbose:
        print(f"{len(claude_msgs)} messages")

    if verbose:
        print("  Reading Codex sessions...", end=" ", flush=True)
    codex_msgs = extract_codex_messages(since)
    if verbose:
        print(f"{len(codex_msgs)} messages")

    all_msgs = claude_msgs + codex_msgs
    all_msgs.sort(key=lambda m: m["ts"])
    return all_msgs


def main():
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="SelfOS Bootstrap — build a self-portrait from AI conversation history"
    )
    parser.add_argument("--days", type=int, default=0,
                        help="Only include sessions from the last N days (default: all)")
    parser.add_argument("--full", action="store_true",
                        help="Force full re-extraction (ignore last-run state)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview extraction without writing any files")
    args = parser.parse_args()

    vault = Path("./vault").resolve()
    inbox = vault / "90_Inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    print("SelfOS Bootstrap")

    # Ensure vault structure is complete
    created = ensure_vault_structure(vault)
    if created:
        print("  Created missing vault structure:")
        for item in created:
            print(item)

    # Auto-install /digest skill
    if install_skill():
        print("  /digest skill: ready")
    else:
        print("  /digest skill: not found (skill file missing)")

    state = load_state(vault)
    since = resolve_since(args.days, args.full, state)

    if args.days > 0:
        print(f"Extracting sessions from the last {args.days} days...")
    elif since is None:
        print("Extracting all sessions (full mode)...")
    else:
        print(f"Extracting sessions since last run ({since.strftime('%Y-%m-%d %H:%M UTC')})...")

    all_msgs = run_extraction(vault, since)

    if not all_msgs:
        print("\nNo new messages since last run.")
        if since:
            print("Run with --full to re-extract everything.")
        return

    if args.dry_run:
        contexts = len(set(m["cwd"] or m["project"] for m in all_msgs))
        oldest = min(m["ts"] for m in all_msgs).strftime("%Y-%m-%d")
        newest = max(m["ts"] for m in all_msgs).strftime("%Y-%m-%d")
        print(f"\n[dry-run] Would write: vault/90_Inbox/{date.today()}-sessions-digest.md")
        print(f"  Messages : {len(all_msgs)}")
        print(f"  Contexts : {contexts}")
        print(f"  Date range: {oldest} → {newest}")
        print("  (no files written)")
        return

    digest = build_session_digest(all_msgs)
    out_path = inbox / f"{date.today()}-sessions-digest.md"
    out_path.write_text(digest, encoding="utf-8")

    # Persist last-run timestamp (use the latest message timestamp)
    latest_msg_ts = max(m["ts"] for m in all_msgs)
    state["last_run"] = latest_msg_ts.isoformat()
    save_state(vault, state)

    # Clean up old digests (keep last 7)
    deleted = cleanup_old_digests(inbox, keep=7)
    if deleted:
        print(f"  Cleaned up {deleted} old digest(s).")

    print(f"\nDone. {len(all_msgs)} messages across {len(set(m['cwd'] or m['project'] for m in all_msgs))} contexts.")
    print(f"Digest: vault/90_Inbox/{out_path.name}")
    print()
    print("Next — open Claude Code in this directory and say:")
    print(f'  "Read vault/90_Inbox/{out_path.name} and distribute insights to vault modules."')


if __name__ == "__main__":
    main()
