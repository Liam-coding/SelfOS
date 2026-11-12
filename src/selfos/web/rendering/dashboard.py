"""web / rendering / dashboard responsibilities."""
from selfos.web.rendering.resources import frontend_text, render_ui
from selfos.web.i18n import runtime, translate
from html import escape
import json
from pathlib import Path
from datetime import date
from selfos.knowledge.scoring import SCORE_DIMENSIONS
from selfos.knowledge.scoring import load_scores

_I18N = {key: 'ui.dimension.'+key for key, _, _ in SCORE_DIMENSIONS}
_STATUS_I18N = {key: 'ui.status.'+key for key in ('great','ok','watch','poor','nodata')}


def _suggestion(key, value):
    if value is None or key not in _I18N:
        return 'ui.suggestion.empty'
    band = 'high' if value >= 7 else 'mid' if value >= 4 else 'low'
    return 'ui.suggestion.'+key+'.'+band


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
    from selfos.web.rendering.onboarding import CONTROLS as onboarding_controls
    knowledge_controls += onboarding_controls
    from selfos.web.rendering.overall import STYLE as selfos_style, OVERVIEW as knowledge_overview
    from selfos.web.rendering.library import STYLE as library_style, HTML as library_html
    """
    Generate dashboard.html one level above vault/ — keyed, localized UI,
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

    # Build dimension cards — embed catalog keys and numeric data
    cards_html = ""
    for key, _label_text, _ in SCORE_DIMENSIONS:
        v = scores.get(key) if scores else None
        if v == "skip":
            continue
        color = score_color(v if isinstance(v, int) else None)
        display = str(v) if isinstance(v, int) else "—"
        skey = status_key(v if isinstance(v, int) else None)
        status_text = escape(translate(_STATUS_I18N[skey]))
        label_text = escape(translate(_I18N[key]))
        sugg = _suggestion(key, v if isinstance(v, int) else None)
        # SVG ring: r=28, circumference=2π*28≈175.9
        r = 28
        circ = 3.14159 * 2 * r
        arc = round((v / 10) * circ, 2) if isinstance(v, int) else 0
        hist_json = json.dumps(dim_history(key))
        cards_html += render_ui('templates/dashboard-card.html', {
            'key': key,
            'label_text': label_text,
            'display': display,
            'score_params': escape(json.dumps({'value':v if isinstance(v,int) else display}),quote=True),
            'color': color,
            'status_text': status_text,
            'suggestion_text': escape(translate(sugg)),
            'label_key': _I18N[key], 'status_key': _STATUS_I18N[skey], 'sugg_key': sugg,
            'r': r,
            'arc': arc,
            'circ': circ,
            'hist_json': hist_json,
        })

    overall_color = score_color(int(overall) if overall and overall >= 1 else None)
    overall_display = str(overall) if overall is not None else "—"
    overall_skey = status_key(int(overall) if overall and overall >= 1 else None)
    overall_status_text = escape(translate(_STATUS_I18N[overall_skey]))
    updated = date.today().isoformat()
    scored_count = len([v for v in (scores or {}).values() if isinstance(v, int)])

    # Overall ring (160×160, r=68)
    r_big = 68
    circ_big = round(3.14159 * 2 * r_big, 2)
    overall_int = int(overall) if overall and overall >= 1 else 0
    arc_big = round((overall_int / 10) * circ_big, 2) if overall_int else 0

    greeting_key = 'ui.dashboard.greeting' if preferred_name else 'ui.dashboard.hello'
    greeting_params = {'name': preferred_name} if preferred_name else {}
    greeting_text = escape(translate(greeting_key, params=greeting_params))

    html = render_ui('templates/dashboard-page.html', {
        'selfos_style': runtime()+selfos_style,
        'library_style': library_style,
        'knowledge_controls': knowledge_controls,
        'knowledge_overview': knowledge_overview,
        'library_html': library_html,
        'greeting_text': greeting_text,
        'greeting_key': greeting_key, 'greeting_params': escape(json.dumps(greeting_params), quote=True),
        'overall_status_key': _STATUS_I18N[overall_skey],
        'r_big': r_big,
        'overall_color': overall_color,
        'arc_big': arc_big,
        'circ_big': circ_big,
        'overall_display': overall_display,
        'overall_params': escape(json.dumps({'value':overall if overall is not None else overall_display}),quote=True),
        'overall_status_text': overall_status_text,
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
