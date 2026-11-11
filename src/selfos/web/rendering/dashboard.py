"""web / rendering / dashboard responsibilities."""
from selfos.web.rendering.resources import frontend_text, render_ui
import json
from pathlib import Path
from datetime import date
from selfos.knowledge.scoring import SCORE_DIMENSIONS
from selfos.knowledge.scoring import load_scores

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
    from selfos.web.rendering.knowledge import CONTROLS as knowledge_controls
    from selfos.web.rendering.model import CONTROLS as model_controls
    knowledge_controls += model_controls
    from selfos.web.rendering.overall import STYLE as selfos_style, OVERVIEW as knowledge_overview
    from selfos.web.rendering.library import STYLE as library_style, HTML as library_html
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
        cards_html += render_ui('templates/dashboard-card.html', {
            'key': key,
            'label_zh': label_zh,
            'label_en': label_en,
            'display': display,
            'color': color,
            'status_zh': status_zh,
            'status_en': status_en,
            'sugg_zh': sugg['zh'],
            'sugg_en': sugg['en'],
            'r': r,
            'arc': arc,
            'circ': circ,
            'hist_json': hist_json,
        })

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

    html = render_ui('templates/dashboard-page.html', {
        'selfos_style': selfos_style,
        'library_style': library_style,
        'knowledge_controls': knowledge_controls,
        'knowledge_overview': knowledge_overview,
        'library_html': library_html,
        'greeting_zh': greeting_zh,
        'greeting_en': greeting_en,
        'r_big': r_big,
        'overall_color': overall_color,
        'arc_big': arc_big,
        'circ_big': circ_big,
        'overall_display': overall_display,
        'overall_status_zh': overall_status_zh,
        'overall_status_en': overall_status_en,
        'scored_count': scored_count,
        'updated': updated,
        'cards_html': cards_html,
    })

    out = vault.parent / "dashboard.html"
    from selfos.web.rendering.overall import integrate_overall
    html = integrate_overall(html)
    out.write_text(html, encoding="utf-8")
    return out


STATE_FILE_NAME = ".bootstrap_state.json"
