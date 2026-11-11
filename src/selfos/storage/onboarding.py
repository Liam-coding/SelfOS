"""storage / onboarding responsibilities."""
from pathlib import Path

def install_skill() -> bool:
    """Copy .claude/skills/digest to ~/.claude/skills/. Returns True if installed."""
    from selfos.paths import resource
    src = resource('skills', 'digest')
    dst = Path.home() / ".claude" / "skills" / "digest"
    if not src.is_dir():
        return False
    if dst.exists():
        return True  # already installed
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        if entry.is_file(): (dst / entry.name).write_bytes(entry.read_bytes())
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

    from selfos.paths import resource
    templates_src = resource('templates')
    for fname in VAULT_FILES:
        dest = vault / fname
        if not dest.exists():
            src = templates_src / fname
            if src.is_file():
                dest.write_bytes(src.read_bytes())
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
