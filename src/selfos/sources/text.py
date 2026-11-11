"""sources / text responsibilities."""
import re

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
