#!/usr/bin/env python3
"""
SelfOS Harvest — Build a self-portrait from your AI conversation history.

Usage:
    python harvest.py           # extract all sessions, write to ./vault
    python harvest.py --days 30 # last 30 days only
    python harvest.py --stats   # show per-project statistics
    python harvest.py --dry-run # preview without writing
    python harvest.py --full    # re-extract everything

The script reads Claude Code and Codex session files, extracts your messages,
filters sensitive data, and writes a digest to vault/90_Inbox/.

Your AI agent then reads the digest and distributes insights across vault modules.
Nothing is written to canonical vault files without your approval.
"""

__version__ = "0.5.0"

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


def extract_claude_messages(since: datetime | None = None) -> tuple[list[dict], int]:
    """
    Extract user messages from all Claude Code session files.
    Returns (messages, raw_user_line_count).
    """
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        return [], 0

    messages = []
    raw_count = 0
    for proj_dir in claude_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        project_name = _decode_claude_project_name(proj_dir.name)

        for session_file in proj_dir.glob("*.jsonl"):
            if not _file_mtime_ok(session_file, since):
                continue
            try:
                with open(session_file, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        obj = json.loads(line)
                        if obj.get("type") != "user":
                            continue
                        raw_count += 1
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

    return messages, raw_count


def extract_codex_messages(since: datetime | None = None) -> tuple[list[dict], int]:
    """
    Extract user messages from all Codex session files.
    Returns (messages, raw_user_line_count).
    """
    sessions_dir = Path.home() / ".codex" / "sessions"
    if not sessions_dir.exists():
        return [], 0

    messages = []
    raw_count = 0
    for session_file in sessions_dir.rglob("*.jsonl"):
        if not _file_mtime_ok(session_file, since):
            continue
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

                    raw_count += 1
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

    return messages, raw_count


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


def _file_mtime_ok(path: Path, since: datetime | None) -> bool:
    """Return True if the file might contain messages newer than `since`.

    Uses file mtime as a cheap pre-filter. A file modified before `since`
    cannot contain new messages. Always returns True when since is None.
    """
    if since is None:
        return True
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return mtime >= since
    except OSError:
        return True  # can't stat → assume relevant


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
source: harvest-discover-{date.today()}
---

# Workspace Discovery Report

## Claude Code workspaces
{claude_lines}

## Codex workspaces
{codex_lines}

## All unique workspaces ({len(discovered['all'])} total)
{chr(10).join(f'  - {p}' for p in discovered['all']) or '  (none found)'}

## Next step
    python harvest.py --sessions --vault ./vault
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
source: harvest-{date.today()}
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

## Notes from harvest scan
{('- Found repos: ' + ', '.join(repos)) if repos else '- No repos detected'}
{('- Project description: ' + description) if description else ''}
"""


def _build_project_draft(workspace, stack, description):
    return f"""---
type: project-context
updated: {date.today()}
source: harvest-{date.today()}
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

# Minimal placeholder content for module directories (created on first run)
_MODULE_PLACEHOLDERS = {
    "01_Career": ("profile.md", "# Career Profile\n\n"
                  "> Fill this in or let your AI update it after `/digest`.\n\n"
                  "## Current Role\n- Title:\n- Company:\n\n"
                  "## Technical Skills\n- \n\n## Career History\n- \n"),
    "02_Work": ("README.md", "# Work\n\n"
                "One file per active project. Example: `myproject.md`\n\n"
                "Let your AI create project files after `/digest`.\n"),
    "03_Research": ("README.md", "# Research\n\n"
                    "One file per research project or paper.\n\n"
                    "Let your AI create research files after `/digest`.\n"),
    "04_Health_Fitness": ("log.md", "# Health & Fitness Log\n\n"
                          "> Append-only. Add dated entries below.\n\n"
                          "## Template\n### YYYY-MM-DD\n- Weight:\n- Training:\n- Notes:\n"),
    "05_Life": ("learning.md", "# Learning\n\n"
                "## Active\n- (course or book — why / by when)\n\n"
                "## Completed\n- YYYY-MM-DD: (what + one-line takeaway)\n"),
    "06_Reviews": ("README.md", "# Reviews\n\n"
                   "Weekly and monthly review files.\n"
                   "Naming: `YYYY-Wnn-weekly.md` or `YYYY-MM-monthly.md`\n"),
}


def ensure_vault_structure(vault: Path) -> list[str]:
    """Create missing vault dirs, root files, and module placeholder files. Returns list of items created."""
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

    # Create module placeholder files
    for module_dir, (fname, content) in _MODULE_PLACEHOLDERS.items():
        dest = vault / module_dir / fname
        if not dest.exists():
            dest.write_text(content, encoding="utf-8")
            created.append(f"  + {module_dir}/{fname}")

    return created


# ── Life score ───────────────────────────────────────────────────────────────

SCORE_DIMENSIONS = [
    ("career",  "职业发展", "01_Career"),
    ("work",    "工作/项目", "02_Work"),
    ("health",  "健康体能",  "04_Health_Fitness"),
    ("learning","学习成长",  "05_Life"),
    ("research","研究",      "03_Research"),
    ("life",    "生活",      "__life__"),   # special: read from root files
    ("family",  "家庭",      None),
]

SCORES_FILE = "SCORES.md"


def _read_vault_text(vault: Path, subdir: str | None) -> str:
    """Return concatenated text of all .md files under vault/subdir (max 3000 chars)."""
    if subdir is None:
        return ""
    target = vault / subdir
    if not target.exists():
        return ""
    texts = []
    for f in sorted(target.glob("*.md")):
        try:
            texts.append(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    combined = "\n".join(texts)
    return combined[:3000]


def _infer_score(text: str, dimension: str) -> int | None:
    """
    Infer a 1-10 score for a life dimension from vault text.
    Returns None when there is not enough *real* content to score.
    Heuristic rules — no external API calls.
    """
    stripped = text.strip() if text else ""
    if len(stripped) < 30:
        return None

    # Detect unfilled templates: skip headers, frontmatter, and placeholder lines.
    # A placeholder line is: bare "-", "- Key:" (nothing after colon),
    # "(description text)", or a line ending with ":"
    content_lines = []
    for l in stripped.splitlines():
        s = l.strip()
        if not s or s.startswith("#") or s.startswith("---") or s.startswith(">"):
            continue
        if s == "-" or s.endswith(":"):
            continue
        if s.startswith("(") and s.endswith(")"):
            continue
        if s.startswith("-") and ":" in s and s.split(":", 1)[-1].strip() == "":
            continue
        content_lines.append(s)

    if len(content_lines) < 10:
        return None

    lower = text.lower()

    # Positive signals (raise score)
    positive_kw = {
        "career":   ["promoted", "offer", "hired", "milestone", "raise", "成功", "晋升", "offer", "机会"],
        "work":     ["shipped", "deployed", "merged", "completed", "done", "发布", "完成", "上线"],
        "health":   ["pr", "pb", "ran", "trained", "workout", "gym", "healthy", "训练", "跑步", "健身"],
        "learning": ["learned", "finished", "course", "certificate", "reading", "学完", "通过", "完成"],
        "research": ["published", "submitted", "paper", "result", "breakthrough", "发表", "投稿", "结果"],
        "life":     ["happy", "enjoying", "balance", "travel", "hobby", "满足", "开心", "平衡"],
        "family":   ["family", "parents", "partner", "kids", "together", "家人", "父母", "伴侣", "孩子"],
    }
    # Negative signals (lower score)
    negative_kw = {
        "career":   ["stuck", "rejected", "fired", "quit", "blocked", "失业", "被拒", "迷茫"],
        "work":     ["blocked", "overdue", "behind", "bug", "crisis", "延期", "阻塞", "压力"],
        "health":   ["injured", "sick", "pain", "fatigue", "skipped", "受伤", "生病", "疼", "跳过"],
        "learning": ["behind", "skipped", "forgot", "stopped", "落后", "停滞"],
        "research": ["stuck", "rejected", "no progress", "blocked", "停滞", "被拒"],
        "life":     ["stressed", "lonely", "anxious", "overwhelmed", "压力", "焦虑", "孤独"],
        "family":   ["conflict", "distant", "argument", "miss", "矛盾", "疏远", "争吵"],
    }

    pos = sum(1 for kw in positive_kw.get(dimension, []) if kw in lower)
    neg = sum(1 for kw in negative_kw.get(dimension, []) if kw in lower)

    # Base score: 5 (neutral), shift by signals
    score = 5 + min(pos, 3) - min(neg, 3)
    return max(1, min(10, score))


def score_vault(vault: Path, skip: list[str] | None = None) -> dict:
    """
    Read vault modules and infer a score (1-10) for each life dimension.
    Returns {dim_key: score_or_None, ...} and writes to SCORES.md.
    skip: list of dimension keys to exclude (e.g. ["family"]).
    """
    skip = skip or []
    scores = {}

    for key, label, subdir in SCORE_DIMENSIONS:
        if key in skip:
            scores[key] = None
            continue
        # Family has no dedicated subdir — extract family-relevant lines from root files
        if subdir is None:
            family_kw = {"family", "parent", "child", "children", "partner", "spouse",
                         "relationship", "home", "girlfriend", "boyfriend",
                         "父母", "孩子", "伴侣", "家人", "家庭", "女朋友", "男朋友"}
            lines = []
            for root_file in ["PROFILE.md", "NOW.md", "GOALS.md"]:
                fp = vault / root_file
                if fp.exists():
                    try:
                        for line in fp.read_text(encoding="utf-8", errors="replace").splitlines():
                            if any(kw in line.lower() for kw in family_kw):
                                lines.append(line)
                    except OSError:
                        pass
            text = "\n".join(lines)
        # Life dimension — general wellbeing from root files + 05_Life
        elif subdir == "__life__":
            parts = []
            for root_file in ["NOW.md", "PROFILE.md", "GOALS.md"]:
                fp = vault / root_file
                if fp.exists():
                    try:
                        parts.append(fp.read_text(encoding="utf-8", errors="replace"))
                    except OSError:
                        pass
            parts.append(_read_vault_text(vault, "05_Life"))
            text = "\n".join(parts)[:3000]
        # Career — subdir files + root PROFILE.md as supplement
        elif key == "career":
            text = _read_vault_text(vault, subdir)
            if len([l for l in text.splitlines() if l.strip()]) < 10:
                fp = vault / "PROFILE.md"
                if fp.exists():
                    try:
                        text = fp.read_text(encoding="utf-8", errors="replace") + "\n" + text
                    except OSError:
                        pass
            text = text[:3000]
        else:
            text = _read_vault_text(vault, subdir)
            # Supplement sparse subdirs with root NOW.md
            if len([l for l in text.splitlines() if l.strip()]) < 10:
                fp = vault / "NOW.md"
                if fp.exists():
                    try:
                        text = text + "\n" + fp.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        pass
            text = text[:3000]

        scores[key] = _infer_score(text, key)

    _append_scores(vault, scores, skip)
    return scores


def _append_scores(vault: Path, scores: dict, skip: list[str]) -> None:
    """Append today's scores to vault/SCORES.md (create if missing).
    If a row for today already exists, replace it instead of appending."""
    scores_path = vault / SCORES_FILE
    today = date.today().isoformat()

    # Build score row
    row_parts = []
    for key, label, _ in SCORE_DIMENSIONS:
        if key in skip:
            row_parts.append(f"{key}: skip")
        elif scores.get(key) is None:
            row_parts.append(f"{key}: null")
        else:
            row_parts.append(f"{key}: {scores[key]}")

    row = f"- {today} | " + " | ".join(row_parts)

    if not scores_path.exists():
        header = (
            "---\n"
            "type: life-scores\n"
            "description: Daily life dimension scores (1-10). Append-only.\n"
            "dimensions: career, work, health, learning, research, life, family\n"
            "---\n\n"
            "# Life Scores\n\n"
            "Each row: `date | dim: score ...` — null = no data, skip = excluded\n\n"
        )
        scores_path.write_text(header + row + "\n", encoding="utf-8")
    else:
        existing = scores_path.read_text(encoding="utf-8")
        lines = existing.splitlines()
        # Replace existing row for today if present
        replaced = False
        new_lines = []
        for line in lines:
            if line.startswith(f"- {today} |"):
                if not replaced:
                    new_lines.append(row)
                    replaced = True
                # skip duplicate rows for today
            else:
                new_lines.append(line)
        if not replaced:
            new_lines.append(row)
        scores_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def load_scores(vault: Path) -> list[dict]:
    """
    Parse SCORES.md and return list of {date, career, work, health, ...} dicts.
    Most recent first.
    """
    scores_path = vault / SCORES_FILE
    if not scores_path.exists():
        return []

    entries = []
    for line in scores_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        line = line[2:]
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        entry = {"date": parts[0]}
        for part in parts[1:]:
            if ":" in part:
                k, v = part.split(":", 1)
                k, v = k.strip(), v.strip()
                if v == "null" or v == "":
                    entry[k] = None
                elif v == "skip":
                    entry[k] = "skip"
                else:
                    try:
                        entry[k] = int(v)
                    except ValueError:
                        entry[k] = None
        entries.append(entry)

    return list(reversed(entries))


# ── Dashboard i18n strings ────────────────────────────────────────────────────

_I18N = {
    "career":   {"zh": "职业发展", "en": "Career"},
    "work":     {"zh": "工作/项目", "en": "Work"},
    "health":   {"zh": "健康体能", "en": "Health"},
    "learning": {"zh": "学习成长", "en": "Learning"},
    "research": {"zh": "研究",     "en": "Research"},
    "life":     {"zh": "生活",     "en": "Life"},
    "family":   {"zh": "家庭",     "en": "Family"},
}

_STATUS_I18N = {
    "great":    {"zh": "良好",   "en": "Great"},
    "ok":       {"zh": "一般",   "en": "OK"},
    "watch":    {"zh": "需关注", "en": "Watch"},
    "poor":     {"zh": "较差",   "en": "Poor"},
    "nodata":   {"zh": "暂无数据","en": "No data"},
}

# Suggestions per dimension per score band (high/mid/low)
_SUGGESTIONS = {
    "career": {
        "high": {"zh": "势头很好，可以开始准备下一步晋升或跳槽计划",
                 "en": "Momentum is strong — consider mapping out your next move"},
        "mid":  {"zh": "明确一个短期职业目标，写进 GOALS.md",
                 "en": "Define one near-term career goal and add it to GOALS.md"},
        "low":  {"zh": "花 30 分钟梳理卡点，写下来，交给 AI 分析",
                 "en": "Spend 30 min mapping blockers — write them down for AI review"},
    },
    "work": {
        "high": {"zh": "项目进展顺利，注意避免范围蔓延",
                 "en": "Projects are flowing — watch for scope creep"},
        "mid":  {"zh": "挑出最重要的一个任务，今天先完成它",
                 "en": "Pick the single most important task and finish it today"},
        "low":  {"zh": "有阻塞项需要清理，更新 NOW.md 的 Blockers 部分",
                 "en": "Clear blockers first — update the Blockers section in NOW.md"},
    },
    "health": {
        "high": {"zh": "保持节奏，记录训练数据有助于发现规律",
                 "en": "Keep the rhythm — logging workouts helps spot patterns"},
        "mid":  {"zh": "增加一次每周训练，睡眠和饮食是基础",
                 "en": "Add one more weekly session; sleep and nutrition are the base"},
        "low":  {"zh": "先从最小行动开始：每天走路 20 分钟",
                 "en": "Start small: 20 min walk every day is a real baseline"},
    },
    "learning": {
        "high": {"zh": "学习节奏好，考虑输出一篇总结巩固理解",
                 "en": "Good pace — write a short summary to solidify understanding"},
        "mid":  {"zh": "设定每周固定学习时间块，保护它不被会议占用",
                 "en": "Block weekly learning time — protect it from meetings"},
        "low":  {"zh": "把当前在学的东西更新进 05_Life/learning.md",
                 "en": "Update what you're learning in 05_Life/learning.md"},
    },
    "research": {
        "high": {"zh": "进展好，及时记录假设和结果，防止遗忘",
                 "en": "Good progress — log hypotheses and results before they fade"},
        "mid":  {"zh": "确定下一个最小可验证的实验，写进 03_Research/",
                 "en": "Define the next smallest verifiable experiment in 03_Research/"},
        "low":  {"zh": "研究停滞时，先整理文献笔记，重新找到节奏",
                 "en": "When stuck, organize reading notes — it restores momentum"},
    },
    "life": {
        "high": {"zh": "生活状态好，记录让你开心的事，以后参考",
                 "en": "Life feels good — note what's working for future reference"},
        "mid":  {"zh": "找一件小事改善生活质量：睡前仪式、户外时间",
                 "en": "Find one small upgrade: a bedtime ritual, outdoor time"},
        "low":  {"zh": "减少一件让你压力大的事，哪怕只是暂停",
                 "en": "Remove one stressor — even pausing something counts"},
    },
    "family": {
        "high": {"zh": "家庭关系稳健，保持主动联系的习惯",
                 "en": "Family bonds are strong — keep the habit of reaching out"},
        "mid":  {"zh": "安排一次和家人的专属时间，不谈工作",
                 "en": "Schedule dedicated family time — no work talk"},
        "low":  {"zh": "发一条消息给重要的人，今天就发",
                 "en": "Send a message to someone important — do it today"},
    },
}


def _suggestion(key: str, v: int | None) -> dict:
    """Return {zh, en} suggestion string for a dimension and score."""
    if v is None or key not in _SUGGESTIONS:
        return {"zh": "填充 vault 内容后自动生成建议", "en": "Add vault content to get suggestions"}
    band = "high" if v >= 7 else ("mid" if v >= 4 else "low")
    return _SUGGESTIONS[key][band]


# ── Dashboard ─────────────────────────────────────────────────────────────────

def _vault_preferred_name(vault: Path) -> str:
    """Read Preferred name from vault/PROFILE.md; fallback to empty string."""
    profile = vault / "PROFILE.md"
    if not profile.exists():
        return ""
    for line in profile.read_text(encoding="utf-8").splitlines():
        if line.strip().lower().startswith("- preferred name:"):
            val = line.split(":", 1)[-1].strip()
            return val if val else ""
    return ""


def generate_dashboard(vault: Path, scores: dict | None = None) -> Path:
    """
    Generate dashboard.html one level above vault/ — bilingual (zh/en toggle),
    with per-dimension suggestions. Returns the path written.
    """
    history = load_scores(vault)
    if scores is None and history:
        latest = history[0]
        scores = {k: v for k, v in latest.items() if k != "date"}

    preferred_name = _vault_preferred_name(vault)

    # Compute overall score
    if scores:
        vals = [v for v in scores.values() if isinstance(v, int)]
        overall = round(sum(vals) / len(vals), 1) if vals else None
    else:
        overall = None

    # Sparkline data: last 14 entries oldest→newest
    chart_entries = list(reversed(history[:14]))

    def dim_history(key):
        return [e.get(key) if isinstance(e.get(key), int) else None for e in chart_entries]

    def score_color(v):
        if v is None:
            return "#6b7280"
        if v >= 8: return "#22c55e"
        if v >= 6: return "#eab308"
        if v >= 4: return "#f97316"
        return "#ef4444"

    def status_key(v):
        if v is None: return "nodata"
        if v >= 8: return "great"
        if v >= 6: return "ok"
        if v >= 4: return "watch"
        return "poor"

    # Build dimension cards — embed both zh and en strings as data attributes
    cards_html = ""
    for key, _label_zh, _ in SCORE_DIMENSIONS:
        v = scores.get(key) if scores else None
        if v == "skip":
            continue
        color = score_color(v if isinstance(v, int) else None)
        display = str(v) if isinstance(v, int) else "—"
        skey = status_key(v if isinstance(v, int) else None)
        status_zh = _STATUS_I18N[skey]["zh"]
        status_en = _STATUS_I18N[skey]["en"]
        label_zh = _I18N[key]["zh"]
        label_en = _I18N[key]["en"]
        sugg = _suggestion(key, v if isinstance(v, int) else None)
        # SVG ring: r=28, circumference=2π*28≈175.9
        r = 28
        circ = 3.14159 * 2 * r
        arc = round((v / 10) * circ, 2) if isinstance(v, int) else 0
        hist_json = json.dumps(dim_history(key))
        cards_html += f"""
        <div class="card" onclick="openDim(this)" data-key="{key}"
             data-label-zh="{label_zh}" data-label-en="{label_en}"
             data-score="{display}" data-color="{color}"
             data-status-zh="{status_zh}" data-status-en="{status_en}"
             data-sugg-zh="{sugg['zh']}" data-sugg-en="{sugg['en']}">
          <div class="card-header">
            <span class="dim-label" data-zh="{label_zh}" data-en="{label_en}">{label_zh}</span>
          </div>
          <div class="ring-wrap">
            <svg class="ring" viewBox="0 0 72 72" width="72" height="72">
              <circle class="ring-bg" cx="36" cy="36" r="{r}"/>
              <circle class="ring-fill" cx="36" cy="36" r="{r}"
                stroke="{color}"
                stroke-dasharray="{arc} {circ}"
                stroke-dashoffset="0"/>
            </svg>
            <span class="ring-score">{display}</span>
          </div>
          <div class="dim-status" style="color:{color}" data-zh="{status_zh}" data-en="{status_en}">{status_zh}</div>
          <div class="dim-suggestion" data-zh="{sugg['zh']}" data-en="{sugg['en']}">{sugg['zh']}</div>
          <canvas class="sparkline" data-values='{hist_json}' data-color='{color}' width="200" height="36"></canvas>
        </div>"""

    overall_color = score_color(int(overall) if overall and overall >= 1 else None)
    overall_display = str(overall) if overall is not None else "—"
    overall_skey = status_key(int(overall) if overall and overall >= 1 else None)
    overall_status_zh = _STATUS_I18N[overall_skey]["zh"]
    overall_status_en = _STATUS_I18N[overall_skey]["en"]
    updated = date.today().isoformat()
    scored_count = len([v for v in (scores or {}).values() if isinstance(v, int)])

    # Overall ring (160×160, r=68)
    r_big = 68
    circ_big = round(3.14159 * 2 * r_big, 2)
    overall_int = int(overall) if overall and overall >= 1 else 0
    arc_big = round((overall_int / 10) * circ_big, 2) if overall_int else 0

    greeting_zh = f"你好，{preferred_name}" if preferred_name else "你好，Liam"
    greeting_en = f"Hello, {preferred_name}" if preferred_name else "Hello, Liam"

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SelfOS</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 120 40'><text y='32' font-size='32' font-family='-apple-system,BlinkMacSystemFont,SF Pro Display,sans-serif' font-weight='800' letter-spacing='-1'>SelfOS</text></svg>">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{
    font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Segoe UI',sans-serif;
    -webkit-font-smoothing:antialiased;
    min-height:100vh;padding:2.5rem;color:#1d1d1f;
    background:#f5f5f7;
  }}
  /* ── Header ── */
  .header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:2.5rem}}
  .header-left{{display:flex;flex-direction:column;gap:.2rem}}
  .brand{{font-size:3.5rem;font-weight:800;letter-spacing:-.04em;color:#1d1d1f;line-height:1}}
  .slogan{{font-size:.8rem;color:#86868b;font-weight:400;letter-spacing:.01em;margin-top:.15rem}}
  .greeting{{font-size:3rem;font-weight:300;letter-spacing:-.02em;color:#1d1d1f;margin-top:.75rem;line-height:1.15;text-align:right}}
  .header-right{{display:flex;flex-direction:column;align-items:flex-end;gap:.625rem}}
  .header-btns{{display:flex;gap:.5rem;align-items:center}}
  .lang-btn,.harvest-btn,.theme-btn{{
    border-radius:10px;padding:.4rem 1rem;
    font-size:.8rem;font-weight:600;cursor:pointer;transition:all .15s;
    white-space:nowrap
  }}
  .lang-btn{{
    background:rgba(0,0,0,.06);border:1px solid rgba(0,0,0,.1);
    color:#1d1d1f
  }}
  .lang-btn:hover{{background:rgba(0,0,0,.1)}}
  .theme-btn{{
    background:rgba(0,0,0,.06);border:1px solid rgba(0,0,0,.1);
    color:#1d1d1f;font-size:.85rem;padding:.4rem .7rem
  }}
  .theme-btn:hover{{background:rgba(0,0,0,.1)}}
  .harvest-btn{{
    background:rgba(0,125,250,.1);border:1px solid rgba(0,125,250,.25);
    color:#0071e3
  }}
  .harvest-btn:hover{{background:rgba(0,125,250,.18)}}
  /* ── Modal ── */
  .modal-backdrop{{
    display:none;position:fixed;inset:0;background:rgba(0,0,0,.35);
    z-index:200;align-items:center;justify-content:center;backdrop-filter:blur(4px)
  }}
  .modal-backdrop.open{{display:flex}}
  .modal{{
    background:#fff;border-radius:22px;padding:2rem 1.75rem 1.5rem;
    max-width:360px;width:90%;box-shadow:0 24px 80px rgba(0,0,0,.2);
    animation:modal-in .2s ease
  }}
  @keyframes modal-in{{from{{transform:scale(.94);opacity:0}}to{{transform:scale(1);opacity:1}}}}
  .modal-icon{{font-size:2rem;margin-bottom:.75rem;text-align:center}}
  .modal-title{{font-size:1.1rem;font-weight:700;color:#1d1d1f;margin-bottom:.5rem;text-align:center}}
  .modal-body{{font-size:.8rem;color:#515154;line-height:1.65;margin-bottom:1.25rem;text-align:center}}
  .modal-steps{{
    background:#f5f5f7;border-radius:12px;padding:.875rem 1rem;
    margin-bottom:1.25rem;list-style:none;display:flex;flex-direction:column;gap:.45rem
  }}
  .modal-steps li{{font-size:.78rem;color:#1d1d1f;display:flex;align-items:flex-start;gap:.5rem}}
  .modal-steps li::before{{content:"";width:6px;height:6px;border-radius:50%;
    background:#0071e3;flex-shrink:0;margin-top:.35rem}}
  .modal-actions{{display:flex;gap:.625rem;justify-content:flex-end}}
  .modal-cancel{{
    padding:.5rem 1rem;border-radius:10px;border:1px solid rgba(0,0,0,.15);
    background:transparent;color:#515154;font-size:.8rem;font-weight:600;cursor:pointer
  }}
  .modal-confirm{{
    padding:.5rem 1.25rem;border-radius:10px;border:none;
    background:#0071e3;color:#fff;font-size:.8rem;font-weight:600;cursor:pointer;
    transition:background .15s
  }}
  .modal-confirm:hover{{background:#0077ed}}
  /* ── Dark theme ── */
  body.dark{{background:#1c1c1e;color:#f5f5f7}}
  body.dark .brand{{color:#f5f5f7}}
  body.dark .slogan{{color:#8e8e93}}
  body.dark .greeting{{color:#f5f5f7}}
  body.dark .lang-btn,.dark .theme-btn{{
    background:rgba(255,255,255,.08);border-color:rgba(255,255,255,.12);color:#f5f5f7
  }}
  body.dark .lang-btn:hover,.dark .theme-btn:hover{{background:rgba(255,255,255,.14)}}
  body.dark .harvest-btn{{background:rgba(0,125,250,.2);border-color:rgba(0,125,250,.4)}}
  body.dark .card{{background:#2c2c2e;border-color:rgba(255,255,255,.08);
    box-shadow:0 2px 12px rgba(0,0,0,.35)}}
  body.dark .card:hover{{box-shadow:0 4px 20px rgba(0,0,0,.5)}}
  body.dark .dim-label{{color:#8e8e93}}
  body.dark .ring-bg{{stroke:rgba(255,255,255,.1)}}
  body.dark .ring-score{{color:#f5f5f7}}
  body.dark .dim-suggestion{{color:#8e8e93}}
  body.dark .legend{{background:#2c2c2e;border-color:rgba(255,255,255,.08)}}
  body.dark .legend-title{{color:#8e8e93}}
  body.dark .legend-text{{color:#f5f5f7}}
  body.dark .overall-ring-bg{{stroke:rgba(255,255,255,.1)}}
  body.dark .overall-ring-num{{color:rgba(255,255,255,.6)}}
  body.dark .overall-info h2{{color:#8e8e93}}
  body.dark .overall-status{{color:#ebebf0}}
  body.dark .overall-count{{color:#8e8e93}}
  body.dark .overall-date{{color:#636366}}
  body.dark footer{{color:#636366}}
  body.dark .chat-panel{{background:#2c2c2e;border-color:rgba(255,255,255,.1)}}
  body.dark .chat-header{{border-bottom-color:rgba(255,255,255,.08)}}
  body.dark .chat-header-title{{color:#f5f5f7}}
  body.dark .chat-header-sub{{color:#8e8e93}}
  body.dark .chat-messages{{scrollbar-color:rgba(255,255,255,.1) transparent}}
  body.dark .msg-ai{{background:rgba(255,255,255,.07);color:#ebebf0}}
  body.dark .msg-user{{background:#0071e3}}
  body.dark .chat-input{{background:#1c1c1e;border-color:rgba(255,255,255,.12);color:#f5f5f7}}
  body.dark .chat-input:focus{{border-color:#0071e3;background:#1c1c1e}}
  body.dark .chat-input-row{{border-top-color:rgba(255,255,255,.08)}}
  body.dark .modal{{background:#2c2c2e}}
  body.dark .modal-title{{color:#f5f5f7}}
  body.dark .modal-body{{color:#aeaeb2}}
  body.dark .modal-steps{{background:#1c1c1e}}
  body.dark .modal-steps li{{color:#f5f5f7}}
  body.dark .modal-cancel{{border-color:rgba(255,255,255,.15);color:#aeaeb2}}
  /* ── Dim detail modal ── */
  .dim-modal{{max-width:320px}}
  .dim-modal-score{{
    font-size:3.5rem;font-weight:200;letter-spacing:-.04em;line-height:1;
    margin:.25rem 0 .125rem;text-align:center
  }}
  .dim-modal-status{{font-size:.8rem;font-weight:600;text-align:center;margin-bottom:1rem}}
  .dim-modal-sugg{{
    font-size:.82rem;color:#515154;line-height:1.65;
    background:#f5f5f7;border-radius:12px;padding:.875rem 1rem;margin-bottom:1rem
  }}
  body.dark .dim-modal-sugg{{background:#1c1c1e;color:#aeaeb2}}
  .dim-modal-chat{{
    width:100%;padding:.55rem 1rem;border-radius:10px;border:none;
    background:#0071e3;color:#fff;font-size:.8rem;font-weight:600;
    cursor:pointer;transition:background .15s
  }}
  .dim-modal-chat:hover{{background:#0077ed}}
  .card{{cursor:pointer}}
  /* ── Hero ── */
  .hero{{display:flex;align-items:center;margin-bottom:1.75rem;gap:0}}
  .hero-greeting{{flex:1;display:flex;justify-content:flex-end;padding-right:2.5rem}}
  .hero-overall{{flex:1;display:flex;justify-content:flex-start;padding-left:2.5rem}}
  /* ── Overall ring ── */
  .overall{{display:flex;flex-direction:column;align-items:center;gap:.75rem;flex-shrink:0}}
  .overall-ring-wrap{{position:relative;width:160px;height:160px}}
  .overall-ring{{transform:rotate(-90deg)}}
  .overall-ring-bg{{fill:none;stroke:rgba(0,0,0,.07);stroke-width:8}}
  .overall-ring-fill{{fill:none;stroke-width:8;stroke-linecap:round}}
  .overall-ring-score{{
    position:absolute;inset:0;display:flex;flex-direction:column;
    align-items:center;justify-content:center
  }}
  .overall-ring-num{{font-size:2.25rem;font-weight:300;line-height:1;
    color:rgba(0,0,0,.55);letter-spacing:-.02em;font-variant-numeric:tabular-nums}}
  .overall-ring-label{{display:none}}
  .overall-info{{text-align:center}}
  .overall-info h2{{font-size:.75rem;font-weight:500;color:#86868b;margin-bottom:.2rem;text-transform:uppercase;letter-spacing:.08em}}
  .overall-status{{font-size:.85rem;font-weight:500;color:#515154;margin-bottom:.15rem}}
  .overall-count{{font-size:.7rem;color:#86868b}}
  .overall-date{{font-size:.65rem;color:#aeaeb2;margin-top:.3rem}}
  /* ── Cards ── */
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:1rem}}
  .card{{
    background:#fff;border:1px solid rgba(0,0,0,.08);
    border-radius:18px;padding:1.25rem 1.25rem 1rem;
    box-shadow:0 2px 12px rgba(0,0,0,.06);
    transition:box-shadow .2s,transform .2s
  }}
  .card:hover{{box-shadow:0 4px 20px rgba(0,0,0,.1);transform:translateY(-1px)}}
  .card-header{{margin-bottom:.75rem}}
  .dim-label{{font-size:.68rem;font-weight:600;color:#86868b;text-transform:uppercase;letter-spacing:.08em}}
  /* Ring (cards) */
  .ring-wrap{{position:relative;width:72px;height:72px;margin:0 auto .75rem}}
  .ring{{transform:rotate(-90deg)}}
  .ring-bg{{fill:none;stroke:rgba(0,0,0,.07);stroke-width:5}}
  .ring-fill{{fill:none;stroke-width:5;stroke-linecap:round}}
  .ring-score{{
    position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
    font-size:1.25rem;font-weight:600;color:#1d1d1f;letter-spacing:-.03em
  }}
  .dim-status{{font-size:.72rem;font-weight:600;margin-bottom:.4rem;text-align:center}}
  .dim-suggestion{{font-size:.7rem;color:#86868b;line-height:1.5;text-align:center}}
  .sparkline{{display:block;margin-top:.625rem;opacity:.6}}
  /* Legend */
  .legend{{
    background:#fff;border:1px solid rgba(0,0,0,.08);
    border-radius:14px;padding:1.125rem 1.5rem;margin-top:1.25rem;
    display:flex;align-items:center;gap:1.5rem;flex-wrap:wrap;
    box-shadow:0 1px 6px rgba(0,0,0,.04)
  }}
  .legend-title{{font-size:.7rem;font-weight:600;color:#86868b;
    text-transform:uppercase;letter-spacing:.08em;margin-right:.25rem}}
  .legend-item{{display:flex;align-items:center;gap:.45rem}}
  .legend-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
  .legend-text{{font-size:.75rem;color:#1d1d1f;font-weight:500}}
  .legend-range{{font-size:.68rem;color:#86868b;margin-left:.1rem}}
  footer{{margin-top:1.5rem;color:#aeaeb2;font-size:.7rem;text-align:center}}
  a{{color:#0071e3;text-decoration:none}}
  /* ── Chat panel ── */
  .chat-panel{{
    position:fixed;right:1.5rem;bottom:1.5rem;
    width:320px;height:520px;
    background:#fff;border:1px solid rgba(0,0,0,.1);border-radius:20px;
    box-shadow:0 8px 40px rgba(0,0,0,.12);
    display:flex;flex-direction:column;overflow:hidden;
    z-index:100;transition:height .25s cubic-bezier(.4,0,.2,1)
  }}
  .chat-panel.collapsed{{height:52px}}
  .chat-header{{
    padding:.875rem 1.125rem;border-bottom:1px solid rgba(0,0,0,.07);
    display:flex;align-items:center;gap:.625rem;flex-shrink:0;
    cursor:pointer;user-select:none
  }}
  .chat-panel.collapsed .chat-header{{border-bottom-color:transparent}}
  .chat-header-dot{{width:8px;height:8px;border-radius:50%;background:#0071e3;flex-shrink:0}}
  .chat-header-title{{font-size:.8rem;font-weight:600;color:#1d1d1f}}
  .chat-header-sub{{font-size:.68rem;color:#86868b;margin-left:auto}}
  .chat-collapse-btn{{
    width:18px;height:18px;border-radius:50%;border:none;
    background:rgba(0,0,0,.06);color:#86868b;
    font-size:.65rem;cursor:pointer;flex-shrink:0;
    display:flex;align-items:center;justify-content:center;
    transition:transform .2s,background .15s;line-height:1
  }}
  .chat-collapse-btn:hover{{background:rgba(0,0,0,.12)}}
  .chat-panel.collapsed .chat-collapse-btn{{transform:rotate(180deg)}}
  .chat-messages{{
    flex:1;overflow-y:auto;padding:.875rem 1rem;
    display:flex;flex-direction:column;gap:.625rem;
    scroll-behavior:smooth
  }}
  .chat-messages::-webkit-scrollbar{{width:4px}}
  .chat-messages::-webkit-scrollbar-thumb{{background:rgba(0,0,0,.1);border-radius:2px}}
  .msg{{max-width:88%;padding:.55rem .8rem;border-radius:14px;font-size:.8rem;line-height:1.5;word-break:break-word}}
  .msg-user{{
    align-self:flex-end;background:#0071e3;color:#fff;
    border-bottom-right-radius:4px
  }}
  .msg-ai{{
    align-self:flex-start;background:#f5f5f7;color:#1d1d1f;
    border-bottom-left-radius:4px
  }}
  .msg-ai.thinking{{color:#86868b;font-style:italic}}
  .chat-input-row{{
    padding:.75rem;border-top:1px solid rgba(0,0,0,.07);
    display:flex;gap:.5rem;flex-shrink:0
  }}
  .chat-input{{
    flex:1;border:1px solid rgba(0,0,0,.12);border-radius:10px;
    padding:.5rem .75rem;font-size:.8rem;font-family:inherit;
    outline:none;resize:none;background:#f5f5f7;color:#1d1d1f;
    line-height:1.4;max-height:80px;overflow-y:auto
  }}
  .chat-input:focus{{border-color:#0071e3;background:#fff}}
  .chat-send{{
    background:#0071e3;color:#fff;border:none;border-radius:10px;
    width:34px;height:34px;cursor:pointer;flex-shrink:0;
    display:flex;align-items:center;justify-content:center;
    font-size:1rem;transition:background .15s;align-self:flex-end
  }}
  .chat-send:hover{{background:#0077ed}}
  .chat-send:disabled{{background:#aeaeb2;cursor:not-allowed}}
  @media(max-width:900px){{
    .chat-panel{{right:.75rem;width:280px}}
  }}
</style>
</head>
<body>
<div class="header">
  <div class="header-left">
    <div class="brand">SelfOS</div>
    <div class="slogan" data-zh="用简单的方式，管理你的人生"
         data-en="A simpler way to manage your life">用简单的方式，管理你的人生</div>
  </div>
  <div class="header-right">
    <div class="header-btns">
      <button class="harvest-btn" onclick="openHarvestModal()" id="harvest-btn"
              data-zh="⟳ 采集数据" data-en="⟳ Harvest">⟳ 采集数据</button>
      <button class="theme-btn" id="theme-toggle" onclick="toggleTheme()" title="切换主题">☀</button>
      <button class="lang-btn" id="lang-toggle" onclick="toggleLang()">EN</button>
    </div>
  </div>
</div>

<!-- Harvest modal -->
<div class="modal-backdrop" id="harvest-modal">
  <div class="modal">
    <div class="modal-icon">🔍</div>
    <div class="modal-title" data-zh="采集数据" data-en="Harvest Data">采集数据</div>
    <div class="modal-body"
         data-zh="将扫描你的所有 Claude Code 和 Codex 历史，通过 AI 自动分类整理，更新你的评分与 vault 内容。"
         data-en="Scan all your Claude Code and Codex history, classify it with AI, and update your scores and vault.">
      将扫描你的所有 Claude Code 和 Codex 历史，通过 AI 自动分类整理，更新你的评分与 vault 内容。
    </div>
    <ul class="modal-steps">
      <li data-zh="扫描 Claude Code 会话记录" data-en="Scan Claude Code session files">扫描 Claude Code 会话记录</li>
      <li data-zh="扫描 Codex 工作区历史" data-en="Scan Codex workspace history">扫描 Codex 工作区历史</li>
      <li data-zh="AI 分类并评估 7 个维度" data-en="AI classifies and scores 7 dimensions">AI 分类并评估 7 个维度</li>
      <li data-zh="生成最新 dashboard" data-en="Generate updated dashboard">生成最新 dashboard</li>
    </ul>
    <div class="modal-actions">
      <button class="modal-cancel" onclick="closeHarvestModal()"
              data-zh="取消" data-en="Cancel">取消</button>
      <button class="modal-confirm" onclick="confirmHarvest()"
              data-zh="开始采集" data-en="Start Harvest">开始采集</button>
    </div>
  </div>
</div>

<!-- Dimension detail modal -->
<div class="modal-backdrop" id="dim-modal">
  <div class="modal dim-modal">
    <div class="modal-icon" id="dim-modal-icon">📊</div>
    <div class="modal-title" id="dim-modal-title">—</div>
    <div class="dim-modal-score" id="dim-modal-score">—</div>
    <div class="dim-modal-status" id="dim-modal-status">—</div>
    <div class="dim-modal-sugg" id="dim-modal-sugg">—</div>
    <button class="dim-modal-chat" onclick="chatAboutDim()"
            data-zh="和 AI 聊这个维度" data-en="Chat about this">和 AI 聊这个维度</button>
  </div>
</div>

<div class="hero">
  <div class="hero-greeting">
    <div class="greeting" id="greeting-text"
         data-zh="{greeting_zh}" data-en="{greeting_en}">{greeting_zh}</div>
  </div>
  <div class="hero-overall">
    <div class="overall">
      <div class="overall-ring-wrap">
        <svg class="overall-ring" viewBox="0 0 160 160" width="160" height="160">
          <circle class="overall-ring-bg" cx="80" cy="80" r="{r_big}"/>
          <circle class="overall-ring-fill" cx="80" cy="80" r="{r_big}"
            stroke="{overall_color}"
            stroke-dasharray="{arc_big} {circ_big}"
            stroke-dashoffset="0"/>
        </svg>
        <div class="overall-ring-score">
          <span class="overall-ring-num">{overall_display}</span>
          <span class="overall-ring-label" data-zh="综合" data-en="overall">综合</span>
        </div>
      </div>
      <div class="overall-info">
        <h2 id="overall-title" data-zh="综合状态" data-en="Overall">综合状态</h2>
        <p class="overall-status" id="overall-status"
           data-zh="{overall_status_zh}" data-en="{overall_status_en}">{overall_status_zh}</p>
        <p class="overall-count" id="overall-count"
           data-zh="{scored_count} 个维度有数据"
           data-en="{scored_count} dimensions scored">{scored_count} 个维度有数据</p>
        <p class="overall-date" id="overall-date"
           data-zh="更新于 {updated}" data-en="Updated {updated}">更新于 {updated}</p>
      </div>
    </div>
  </div>
</div>

<div class="grid">{cards_html}
</div>

<div class="legend">
  <span class="legend-title" data-zh="评分说明" data-en="Scale">评分说明</span>
  <div class="legend-item">
    <div class="legend-dot" style="background:#ef4444"></div>
    <span class="legend-text" data-zh="较差" data-en="Poor">较差</span>
    <span class="legend-range">1–3</span>
  </div>
  <div class="legend-item">
    <div class="legend-dot" style="background:#f97316"></div>
    <span class="legend-text" data-zh="需关注" data-en="Watch">需关注</span>
    <span class="legend-range">4–5</span>
  </div>
  <div class="legend-item">
    <div class="legend-dot" style="background:#eab308"></div>
    <span class="legend-text" data-zh="一般" data-en="OK">一般</span>
    <span class="legend-range">6–7</span>
  </div>
  <div class="legend-item">
    <div class="legend-dot" style="background:#22c55e"></div>
    <span class="legend-text" data-zh="良好" data-en="Great">良好</span>
    <span class="legend-range">8–10</span>
  </div>
</div>

<footer>SelfOS · <span data-zh="数据来源" data-en="Source">数据来源</span>: vault/ ·
<a href="vault/90_Inbox/"><span data-zh="查看原始摘要" data-en="View digest">查看原始摘要</span></a></footer>

<!-- Chat panel -->
<div class="chat-panel" id="chat-panel">
  <div class="chat-header" onclick="toggleChat()">
    <div class="chat-header-dot"></div>
    <span class="chat-header-title" data-zh="和我聊聊" data-en="Let's talk">和我聊聊</span>
    <span class="chat-header-sub" data-zh="了解你的一切" data-en="knows your story">了解你的一切</span>
    <button class="chat-collapse-btn" id="chat-collapse-btn" onclick="toggleChat(event)">▼</button>
  </div>
  <div class="chat-messages" id="chat-messages">
    <div class="msg msg-ai" data-zh="你好，Liam。今天的评分出来了，有什么想深入聊的维度吗？"
         data-en="Hey Liam. Your scores are in — which dimension do you want to dig into?">你好，Liam。今天的评分出来了，有什么想深入聊的维度吗？</div>
  </div>
  <div class="chat-input-row">
    <textarea class="chat-input" id="chat-input" rows="1"
      placeholder="输入消息…" data-ph-zh="输入消息…" data-ph-en="Type a message…"></textarea>
    <button class="chat-send" id="chat-send" onclick="sendChat()">↑</button>
  </div>
</div>

<script>
// ── Theme ──
let isDark = localStorage.getItem('selfos-theme') === 'dark';
(function() {{
  if (isDark) document.body.classList.add('dark');
  updateThemeBtn();
}})();
function updateThemeBtn() {{
  document.getElementById('theme-toggle').textContent = isDark ? '🌙' : '☀';
}}
function toggleTheme() {{
  isDark = !isDark;
  document.body.classList.toggle('dark', isDark);
  localStorage.setItem('selfos-theme', isDark ? 'dark' : 'light');
  updateThemeBtn();
}}

// ── Language ──
let lang = 'zh';
function toggleLang() {{
  lang = lang === 'zh' ? 'en' : 'zh';
  document.getElementById('lang-toggle').textContent = lang === 'zh' ? 'EN' : '中文';
  document.documentElement.lang = lang;
  document.querySelectorAll('[data-zh][data-en]').forEach(el => {{
    el.textContent = el.dataset[lang];
  }});
  const inp = document.getElementById('chat-input');
  inp.placeholder = lang === 'zh' ? '输入消息…' : 'Type a message…';
}}

// ── Dim icons ──
const DIM_ICONS = {{
  career:'💼', work:'🛠', health:'💪', learning:'📚',
  research:'🔬', life:'🌿', family:'🏠'
}};
let _currentDimKey = '';

function openDim(card) {{
  const key   = card.dataset.key;
  const score = card.dataset.score;
  const color = card.dataset.color;
  _currentDimKey = key;
  const label = card.dataset[lang === 'zh' ? 'labelZh' : 'labelEn'];

  // Show modal
  document.getElementById('dim-modal-icon').textContent  = DIM_ICONS[key] || '📊';
  document.getElementById('dim-modal-title').textContent = label;
  const scoreEl = document.getElementById('dim-modal-score');
  scoreEl.textContent = score;
  scoreEl.style.color = color;
  document.getElementById('dim-modal-status').textContent = card.dataset[lang === 'zh' ? 'statusZh' : 'statusEn'];
  document.getElementById('dim-modal-status').style.color = color;
  document.getElementById('dim-modal-sugg').textContent   = card.dataset[lang === 'zh' ? 'suggZh' : 'suggEn'];
  document.getElementById('dim-modal').classList.add('open');

  // Simultaneously send chat in background
  if (chatCollapsed) toggleChat();
  const msg = lang === 'zh' ? `帮我分析一下「${{label}}」这个维度` : `Tell me about my ${{label}} dimension`;
  _sendChatSilent(msg);
}}
document.getElementById('dim-modal').addEventListener('click', e => {{
  if (e.target === e.currentTarget) document.getElementById('dim-modal').classList.remove('open');
}});

// Send a chat message without touching the input box
async function _sendChatSilent(text) {{
  appendMsg(text, 'user');
  chatHistory.push({{role:'user', content: text}});
  const thinking = appendMsg(lang === 'zh' ? '思考中…' : 'Thinking…', 'ai');
  thinking.classList.add('thinking');
  try {{
    const res = await fetch('/chat', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{messages: chatHistory}})
    }});
    const data = await res.json();
    thinking.remove();
    const reply = data.reply || data.error || 'Error';
    appendMsg(reply, 'ai');
    chatHistory.push({{role:'assistant', content: reply}});
  }} catch(e) {{
    thinking.textContent = lang === 'zh' ? '连接失败，请启动 serve.py' : 'Connection failed — run serve.py';
  }}
}}

// ── Harvest modal ──
function openHarvestModal() {{
  document.getElementById('harvest-modal').classList.add('open');
}}
function closeHarvestModal() {{
  document.getElementById('harvest-modal').classList.remove('open');
}}
function confirmHarvest() {{
  closeHarvestModal();
  const btn = document.getElementById('harvest-btn');
  btn.disabled = true;
  btn.textContent = lang === 'zh' ? '采集中…' : 'Running…';
  fetch('/__harvest__', {{method:'POST'}})
    .catch(() => {{}})
    .finally(() => {{ setTimeout(() => location.reload(), 2500); }});
}}
document.getElementById('harvest-modal').addEventListener('click', e => {{
  if (e.target === e.currentTarget) closeHarvestModal();
}});

// ── Chat collapse ──
let chatCollapsed = false;
function toggleChat(e) {{
  if (e) e.stopPropagation();
  chatCollapsed = !chatCollapsed;
  document.getElementById('chat-panel').classList.toggle('collapsed', chatCollapsed);
}}

// ── Chat ──
const chatHistory = [];
function appendMsg(text, role) {{
  const box = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'msg ' + (role === 'user' ? 'msg-user' : 'msg-ai');
  div.textContent = text;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  return div;
}}
async function sendChat() {{
  const inp = document.getElementById('chat-input');
  const text = inp.value.trim();
  if (!text) return;
  inp.value = '';
  inp.style.height = 'auto';
  document.getElementById('chat-send').disabled = true;

  appendMsg(text, 'user');
  chatHistory.push({{role:'user', content: text}});

  const thinking = appendMsg(lang === 'zh' ? '思考中…' : 'Thinking…', 'ai');
  thinking.classList.add('thinking');

  try {{
    const res = await fetch('/chat', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{messages: chatHistory}})
    }});
    const data = await res.json();
    thinking.remove();
    const reply = data.reply || data.error || 'Error';
    appendMsg(reply, 'ai');
    chatHistory.push({{role:'assistant', content: reply}});
  }} catch(e) {{
    thinking.textContent = lang === 'zh' ? '连接失败，请启动 serve.py' : 'Connection failed — run serve.py';
    thinking.classList.add('thinking');
  }}
  document.getElementById('chat-send').disabled = false;
  inp.focus();
}}
document.getElementById('chat-input').addEventListener('keydown', e => {{
  if (e.key === 'Enter' && !e.shiftKey) {{ e.preventDefault(); sendChat(); }}
}});
document.getElementById('chat-input').addEventListener('input', function() {{
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 80) + 'px';
}});

// Sparkline
document.querySelectorAll('.sparkline').forEach(canvas => {{
  const values = JSON.parse(canvas.dataset.values);
  const color = canvas.dataset.color;
  const ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;
  if (values.filter(v => v !== null).length < 2) return;
  ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.beginPath();
  let first = true;
  values.forEach((v, i) => {{
    if (v === null) {{ first = true; return; }}
    const x = (i / (values.length - 1)) * w;
    const y = h - ((v - 1) / 9) * (h - 4) - 2;
    if (first) {{ ctx.moveTo(x, y); first = false; }} else ctx.lineTo(x, y);
  }});
  ctx.stroke();
}});
</script>
</body>
</html>"""

    out = vault.parent / "dashboard.html"
    out.write_text(html, encoding="utf-8")
    return out


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


def main():
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="SelfOS Harvest — build a self-portrait from AI conversation history"
    )
    parser.add_argument("--days", type=int, default=0,
                        help="Only include sessions from the last N days (default: all)")
    parser.add_argument("--full", action="store_true",
                        help="Force full re-extraction (ignore last-run state)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview extraction without writing any files")
    parser.add_argument("--stats", action="store_true",
                        help="Show per-project statistics without writing any files")
    parser.add_argument("--version", action="version", version=f"harvest {__version__}")
    args = parser.parse_args()

    vault = Path("./vault").resolve()
    inbox = vault / "90_Inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    import time as _time
    _start = _time.monotonic()

    print("SelfOS Harvest")

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

    all_msgs, raw_count = run_extraction(vault, since)

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

    if args.stats:
        print()
        print(build_stats_report(all_msgs))
        return

    digest = build_session_digest(all_msgs, raw_line_count=raw_count)
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

    contexts = len(set(m["cwd"] or m["project"] for m in all_msgs))
    elapsed = _time.monotonic() - _start
    print(f"\nDone in {elapsed:.1f}s: {len(all_msgs)} msgs from {contexts} contexts "
          f"→ vault/90_Inbox/{out_path.name}")

    # Score vault and generate dashboard
    scores = score_vault(vault)
    dash = generate_dashboard(vault, scores)
    scored = [k for k, v in scores.items() if isinstance(v, int)]
    print(f"  Dashboard: {dash.relative_to(vault.parent)} "
          f"({len(scored)} dimensions scored)")

    print()
    print("Next — open Claude Code in this directory and say:")
    print(f'  "Read vault/90_Inbox/{out_path.name} and distribute insights to vault modules."')


if __name__ == "__main__":
    main()
