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
        # keep email only if it looks like a personal one (not corp)
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
            # grab first non-empty paragraph after the title
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
                # skip the title line, take first real paragraph
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


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SelfOS Bootstrap — auto-fill vault from workspace")
    parser.add_argument("--workspace", default=".", help="Workspace directory to scan")
    parser.add_argument("--vault", default="./vault", help="SelfOS vault directory")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    vault = Path(args.vault).resolve()
    staging = vault / "91_Staging"
    staging.mkdir(parents=True, exist_ok=True)

    print(f"🔍 Scanning workspace: {workspace}")
    print(f"📁 Vault: {vault}")
    print()

    git_info = get_git_info(workspace)
    stack = detect_stack(workspace)
    description = extract_project_description(workspace)

    print(f"✓ Git user: {git_info.get('name', 'not found')}")
    print(f"✓ Stack detected: {', '.join(stack) if stack else 'none'}")
    print(f"✓ Repos: {', '.join(git_info.get('github_repos', [])) or 'none'}")
    print()

    today = date.today()

    # Write PROFILE draft
    profile_path = staging / f"{today}-bootstrap-profile.md"
    profile_path.write_text(
        build_profile_draft(git_info, stack, description), encoding="utf-8"
    )
    print(f"📝 Profile draft → {profile_path.relative_to(vault)}")

    # Write project context draft
    project_path = staging / f"{today}-bootstrap-project.md"
    project_path.write_text(
        build_project_draft(workspace, stack, description), encoding="utf-8"
    )
    print(f"📝 Project draft → {project_path.relative_to(vault)}")

    print()
    print("✅ Done. Review the staging files above, then tell your AI agent:")
    print('   "Apply the bootstrap staging files to my vault."')
    print()
    print("⚠️  Nothing has been written to canonical vault files yet.")


if __name__ == "__main__":
    main()
