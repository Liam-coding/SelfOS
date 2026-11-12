"""Contained, bounded onboarding metadata; never canonical knowledge."""
import json
import re
import os
import time
from contextlib import contextmanager
from pathlib import Path

from selfos.storage.files import _atomic_write


def metadata_path(vault, name):
    root = Path(vault).resolve()
    if name not in (".knowledge_sources.json", ".knowledge_onboarding.json") and not re.fullmatch(
            r"\.knowledge_onboarding/(?:previews|budgets)/[a-f0-9]{32}\.json", name):
        raise ValueError("Unsupported onboarding metadata path")
    path = root / name
    if not path.resolve().is_relative_to(root):
        raise ValueError("Onboarding metadata escapes vault")
    return path


def read_metadata(vault, name, default=None, max_bytes=65536):
    path = metadata_path(vault, name)
    if not path.exists():
        return default
    with path.open("rb") as stream:
        data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("Onboarding metadata is too large")
    try:
        return json.loads(data)
    except (ValueError, UnicodeError) as error:
        raise ValueError("Invalid onboarding metadata") from error


def write_metadata(vault, name, value, max_bytes=65536):
    data = json.dumps(value, ensure_ascii=False).encode("utf-8")
    if len(data) > max_bytes:
        raise ValueError("Onboarding metadata is too large")
    _atomic_write(metadata_path(vault, name), data)


class ModelBudgetExceeded(RuntimeError):
    """A new explicit preview/allowance is required for more requests."""


@contextmanager
def _budget_lock(vault, preview_id):
    # Advisory OS locks release on process exit; separate from the import lock.
    path = metadata_path(vault, f".knowledge_onboarding/budgets/{preview_id}.json")
    lock = path.with_suffix(".lock")
    if not lock.resolve().is_relative_to(Path(vault).resolve()):
        raise ValueError("Budget lock escapes vault")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            if stream.seek(0, 2) == 0:
                stream.write(b"0")
                stream.flush()
            deadline = time.monotonic() + 10
            while True:
                stream.seek(0)
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Sample allowance is busy; retry later")
                    time.sleep(0.01)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class SampleBudget:
    def __init__(self, vault, preview_id):
        self.vault = vault
        self.preview_id = preview_id
        self.name = f".knowledge_onboarding/budgets/{preview_id}.json"
        metadata_path(vault, self.name)

    def _read(self):
        value = read_metadata(self.vault, self.name)
        preview = read_metadata(self.vault, f".knowledge_onboarding/previews/{self.preview_id}.json", max_bytes=2 * 1024 * 1024)
        if (not isinstance(value, dict) or value.get("version") != 1
                or not isinstance(preview, dict) or preview.get("id") != self.preview_id
                or type(value.get("used")) is not int or type(value.get("limit")) is not int
                or value["limit"] not in (12, 24) or not 0 <= value["used"] <= value["limit"]
                or value["limit"] != preview.get("budget_limit")):
            raise ValueError("Invalid or missing sample allowance; create a new preview")
        return value

    def status(self):
        with _budget_lock(self.vault, self.preview_id):
            value = self._read()
            return {"used": value["used"], "remaining": value["limit"] - value["used"], "limit": value["limit"]}

    def claim(self):
        with _budget_lock(self.vault, self.preview_id):
            value = self._read()
            if value["used"] >= value["limit"]:
                raise ModelBudgetExceeded("Sample request allowance exhausted; saved progress is retained. Create a new preview to grant more requests.")
            value["used"] += 1
            write_metadata(self.vault, self.name, value)


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
