"""sources / readers responsibilities."""
from selfos.sources.text import _is_meaningful
from selfos.sources.text import _text_from_content
from selfos.sources.text import redact
import re
import json
from pathlib import Path
from datetime import datetime, timezone

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
