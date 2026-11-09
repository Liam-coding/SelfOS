#!/usr/bin/env python3
"""
SelfOS Bootstrap — Auto-fill vault templates from your workspace.

Scans your working directory for context clues (git config, project files,
code patterns), filters out sensitive data, and pre-fills SelfOS vault
templates so you don't start from scratch.

Usage:
    python bootstrap.py                        # scan current directory
    python bootstrap.py --workspace /path/to   # scan specific path
    python bootstrap.py --vault /path/to/vault # write to specific vault
    python bootstrap.py --discover             # auto-discover Claude Code + Codex workspaces

The script NEVER writes directly to canonical vault files.
All output goes to vault/91_Staging/ for your review first.
"""

import os
import re
import json
import argparse
import subprocess
from pathlib import Path
from datetime import date

# ── Sensitive data patterns to filter out ─────────────────────────────────────
SENSITIVE_PATTERNS = [
    r"(?i)(password|passwd|pwd)\s*[=:]\s*\S+",
    r"(?i)(secret|token|api[_-]?key|access[_-]?key)\s*[=:]\s*\S+",
    r"(?i)(private[_-]?key|client[_-]?secret)\s*[=:]\s*\S+",
    r"[A-Za-z0-9+/]{40,}={0,2}",          # base64-like tokens
    r"sk-[A-Za-z0-9]{20,}",               # OpenAI keys
    r"ghp_[A-Za-z0-9]{36}",               # GitHub PATs
    r"xox[baprs]-[A-Za-z0-9-]+",          # Slack tokens
    r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",     # phone numbers
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # emails
]

SENSITIVE_RE = [re.compile(p) for p in SENSITIVE_PATTERNS]


def is_sensitive(value: str) -> bool:
    return any(r.search(value) for r in SENSITIVE_RE)


def redact(value: str) -> str:
    for r in SENSITIVE_RE:
        value = r.sub("[REDACTED]", value)
    return value


# ── Workspace auto-discovery ──────────────────────────────────────────────────

def _decode_claude_project_path(dir_name: str) -> Path | None:
    """
    Claude Code encodes project paths as directory names.
    Encoding: drive letter becomes "X--", path separators become "-".
    Example: "C--Users-foo-myproject" -> C:\\Users\\foo\\myproject
    """
    # Match drive prefix: one or two uppercase letters followed by --
    m = re.match(r'^([A-Za-z]{1,2})--(.*)$', dir_name)
    if not m:
        return None
    drive = m.group(1).upper() + ":"
    rest = m.group(2).replace("-", os.sep)
    p = Path(drive + os.sep + rest)
    return p if p.exists() else None


def discover_claude_workspaces() -> list[Path]:
    """Return all project directories that Claude Code has been used in."""
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
    """
    Codex doesn't store workspace paths directly.
    We recover them from recent session history (cwd field in turn records).
    """
    workspaces = set()

    # 1. OPENAI_CODEX_WORKSPACE env var (if set)
    env_ws = os.environ.get("OPENAI_CODEX_WORKSPACE")
    if env_ws:
        p = Path(env_ws)
        if p.is_dir():
            workspaces.add(p)

    # 2. Parse session_index + recent session files for cwd paths
    codex_dir = Path.home() / ".codex"
    sessions_dir = codex_dir / "sessions"
    index_file = codex_dir / "session_index.jsonl"

    if index_file.exists() and sessions_dir.exists():
        try:
            with open(index_file, encoding="utf-8", errors="ignore") as f:
                session_ids = []
                for line in f:
                    try:
                        obj = json.loads(line)
                        if "id" in obj:
                            session_ids.append(obj["id"])
                    except json.JSONDecodeError:
                        continue

            # Check the most recent 20 sessions for cwd info
            for sid in reversed(session_ids[-20:]):
                session_path = _find_codex_session_file(sessions_dir, sid)
                if not session_path:
                    continue
                try:
                    content = session_path.read_text(encoding="utf-8", errors="ignore")
                    # Look for cwd or workdir fields in the session JSON/JSONL
                    for match in re.finditer(r'"(?:cwd|workdir|workspace)"\s*:\s*"([^"]+)"', content):
                        p = Path(match.group(1))
                        if p.is_dir():
                            workspaces.add(p)
                except Exception:
                    continue
        except Exception:
            pass

    return sorted(workspaces)


def _find_codex_session_file(sessions_dir: Path, session_id: str) -> Path | None:
    """Find the session file for a given session ID (may be nested by year)."""
    # sessions/<year>/<session_id>.jsonl or sessions/<session_id>.jsonl
    for candidate in [
        sessions_dir / f"{session_id}.jsonl",
        *sessions_dir.rglob(f"{session_id}.jsonl"),
    ]:
        if candidate.exists():
            return candidate
    return None


def discover_all_workspaces() -> dict[str, list[Path]]:
    """Auto-discover all Claude Code and Codex workspaces."""
    claude_ws = discover_claude_workspaces()
    codex_ws = discover_codex_workspaces()

    # Deduplicate: if same path appears in both, show once
    all_paths = set(claude_ws) | set(codex_ws)
    return {
        "claude": claude_ws,
        "codex": codex_ws,
        "all": sorted(all_paths),
    }


# ── Git context ───────────────────────────────────────────────────────────────

def get_git_info(workspace: Path) -> dict:
    info = {}
    try:
        name = subprocess.check_output(
            ["git", "config", "user.name"], cwd=workspace, text=True
        ).strip()
        if name and not is_sensitive(name):
            info["name"] = name

        email = subprocess.check_output(
            ["git", "config", "user.email"], cwd=workspace, text=True
        ).strip()
        if email and not is_sensitive(email):
            info["email"] = email

        remotes = subprocess.check_output(
            ["git", "remote", "-v"], cwd=workspace, text=True
        ).strip()
        repos = re.findall(r"github\.com[:/]([^/\s]+/[^\s.]+)", remotes)
        if repos:
            info["github_repos"] = list(set(repos))

    except Exception:
        pass
    return info


# ── Project language / stack detection ───────────────────────────────────────

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


# ── README / project description ──────────────────────────────────────────────

def extract_project_description(workspace: Path) -> str:
    for name in ["README.md", "README.rst", "README.txt"]:
        readme = workspace / name
        if readme.exists():
            content = readme.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
            paragraphs = []
            current = []
            for line in lines:
                if line.strip():
                    current.append(line.strip())
                elif current:
                    paragraphs.append(" ".join(current))
                    current = []
            if paragraphs:
                for p in paragraphs:
                    if not p.startswith("#"):
                        return redact(p[:300])
    return ""


# ── Build staging output ──────────────────────────────────────────────────────

def build_profile_draft(git_info: dict, stack: list, description: str) -> str:
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
- Team: [fill in]
- Start date: [fill in]

## Technical Strengths
- {stack_str}

## Long-Term Goals
- [fill in]

## GitHub
- {github}

## Notes from bootstrap scan
{('- Found repos: ' + ', '.join(repos)) if repos else '- No repos detected'}
{('- Project description: ' + description) if description else ''}
"""


def build_project_draft(workspace: Path, stack: list, description: str) -> str:
    project_name = workspace.name
    return f"""---
type: project-context
updated: {date.today()}
source: bootstrap-{date.today()}
---

# Project Context

## Active Projects

### {project_name}
- **Status**: in progress
- **Stack**: {', '.join(stack) if stack else '[fill in]'}
- **Description**: {description if description else '[fill in]'}
- **Goal**: [what done looks like]
- **Next action**: [concrete next step]

## Notes
- Scanned from: {workspace}
- Review and fill in the blanks before applying to canonical files.
"""


def build_discovery_report(discovered: dict[str, list[Path]]) -> str:
    claude_lines = "\n".join(f"  - {p}" for p in discovered["claude"]) or "  (none found)"
    codex_lines = "\n".join(f"  - {p}" for p in discovered["codex"]) or "  (none found)"
    all_lines = "\n".join(f"  - {p}" for p in discovered["all"]) or "  (none found)"

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
{all_lines}

## Next step
Pick the workspaces that represent active projects and run:
    python bootstrap.py --workspace <path> --vault ./vault

Or pass all at once with --workspaces (space-separated).
"""


# ── Main ──────────────────────────────────────────────────────────────────────

def scan_workspace(workspace: Path, vault: Path, label: str = "") -> None:
    staging = vault / "91_Staging"
    staging.mkdir(parents=True, exist_ok=True)

    tag = f"-{label}" if label else ""
    prefix = f"{date.today()}{tag}-{workspace.name}"

    print(f"\n{'='*60}")
    print(f"Scanning: {workspace}")
    print(f"{'='*60}")

    git_info = get_git_info(workspace)
    stack = detect_stack(workspace)
    description = extract_project_description(workspace)

    print(f"  Git user : {git_info.get('name', 'not found')}")
    print(f"  Stack    : {', '.join(stack) if stack else 'none'}")
    print(f"  Repos    : {', '.join(git_info.get('github_repos', [])) or 'none'}")

    profile_path = staging / f"{prefix}-profile.md"
    profile_path.write_text(build_profile_draft(git_info, stack, description), encoding="utf-8")
    print(f"  Profile draft  : {profile_path.relative_to(vault)}")

    project_path = staging / f"{prefix}-project.md"
    project_path.write_text(build_project_draft(workspace, stack, description), encoding="utf-8")
    print(f"  Project draft  : {project_path.relative_to(vault)}")


def main():
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="SelfOS Bootstrap — auto-fill vault from workspace")
    parser.add_argument("--workspace", help="Single workspace directory to scan")
    parser.add_argument("--workspaces", nargs="+", help="Multiple workspace directories to scan")
    parser.add_argument("--vault", default="./vault", help="SelfOS vault directory")
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Auto-discover Claude Code and Codex workspaces, write a discovery report to staging",
    )
    args = parser.parse_args()

    vault = Path(args.vault).resolve()
    staging = vault / "91_Staging"
    staging.mkdir(parents=True, exist_ok=True)

    print(f"SelfOS Bootstrap")
    print(f"Vault: {vault}")

    if args.discover:
        print("\nDiscovering workspaces from Claude Code and Codex...")
        discovered = discover_all_workspaces()
        print(f"  Claude Code: {len(discovered['claude'])} workspace(s)")
        print(f"  Codex:       {len(discovered['codex'])} workspace(s)")
        print(f"  Total unique: {len(discovered['all'])}")

        report_path = staging / f"{date.today()}-discovery-report.md"
        report_path.write_text(build_discovery_report(discovered), encoding="utf-8")
        print(f"\n  Discovery report: {report_path.relative_to(vault)}")
        print("\nReview the report, then re-run with --workspaces to scan specific ones.")
        print("Or scan all discovered workspaces now:")
        print("  python bootstrap.py --workspaces " + " ".join(f'"{p}"' for p in discovered["all"]))
        return

    workspaces = []
    if args.workspaces:
        workspaces = [Path(w).resolve() for w in args.workspaces]
    elif args.workspace:
        workspaces = [Path(args.workspace).resolve()]
    else:
        workspaces = [Path(".").resolve()]

    for ws in workspaces:
        if not ws.is_dir():
            print(f"Warning: {ws} is not a directory, skipping.")
            continue
        scan_workspace(ws, vault)

    print(f"\n{'='*60}")
    print(f"Done. {len(workspaces)} workspace(s) scanned.")
    print("Review the staging files above, then tell your AI agent:")
    print('  "Apply the bootstrap staging files to my vault."')
    print()
    print("Nothing has been written to canonical vault files yet.")


if __name__ == "__main__":
    main()
