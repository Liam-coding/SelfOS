"""knowledge / scoring responsibilities."""
from pathlib import Path
from datetime import date

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
