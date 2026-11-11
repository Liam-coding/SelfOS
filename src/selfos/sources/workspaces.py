"""sources / workspaces responsibilities."""
import os
import re
import json
import subprocess
from pathlib import Path
from datetime import date
from selfos.sources.text import is_sensitive
from selfos.sources.text import redact

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
    python -m selfos harvest --sessions --vault ./vault
"""


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
