"""web / rendering / dashboard responsibilities."""
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
        cards_html += f"""
        <div class="card" onclick="openDim(this)" data-key="{key}"
             data-label-zh="{label_zh}" data-label-en="{label_en}"
             data-score="{display}" data-color="{color}"
             data-status-zh="{status_zh}" data-status-en="{status_en}"
             data-sugg-zh="{sugg['zh']}" data-sugg-en="{sugg['en']}">
          <div class="card-header">
            <span class="dim-label" data-zh="{label_zh}" data-en="{label_en}">{label_zh}</span>
          </div>
          <div class="ring-wrap">
            <svg class="ring" viewBox="0 0 72 72" width="72" height="72">
              <circle class="ring-bg" cx="36" cy="36" r="{r}"/>
              <circle class="ring-fill" cx="36" cy="36" r="{r}"
                stroke="{color}"
                stroke-dasharray="{arc} {circ}"
                stroke-dashoffset="0"/>
            </svg>
            <span class="ring-score">{display}</span>
          </div>
          <div class="dim-status" style="color:{color}" data-zh="{status_zh}" data-en="{status_en}">{status_zh}</div>
          <div class="dim-suggestion" data-zh="{sugg['zh']}" data-en="{sugg['en']}">{sugg['zh']}</div>
          <canvas class="sparkline" data-values='{hist_json}' data-color='{color}' width="200" height="36"></canvas>
        </div>"""

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

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SelfOS</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 120 40'><text y='32' font-size='32' font-family='-apple-system,BlinkMacSystemFont,SF Pro Display,sans-serif' font-weight='800' letter-spacing='-1'>SelfOS</text></svg>">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{
    font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Segoe UI',sans-serif;
    -webkit-font-smoothing:antialiased;
    min-height:100vh;padding:2.5rem;color:#1d1d1f;
    background:#f5f5f7;
  }}
  /* ── Header ── */
  .header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:2.5rem}}
  .header-left{{display:flex;flex-direction:column;gap:.2rem}}
  .brand{{font-size:3.5rem;font-weight:800;letter-spacing:-.04em;color:#1d1d1f;line-height:1}}
  .slogan{{font-size:.8rem;color:#86868b;font-weight:400;letter-spacing:.01em;margin-top:.15rem}}
  .greeting{{font-size:3rem;font-weight:300;letter-spacing:-.02em;color:#1d1d1f;margin-top:.75rem;line-height:1.15;text-align:right}}
  .header-right{{display:flex;flex-direction:column;align-items:flex-end;gap:.625rem}}
  .header-btns{{display:flex;gap:.5rem;align-items:center}}
  .lang-btn,.harvest-btn,.theme-btn{{
    border-radius:10px;padding:.4rem 1rem;
    font-size:.8rem;font-weight:600;cursor:pointer;transition:all .15s;
    white-space:nowrap
  }}
  .lang-btn{{
    background:rgba(0,0,0,.06);border:1px solid rgba(0,0,0,.1);
    color:#1d1d1f
  }}
  .lang-btn:hover{{background:rgba(0,0,0,.1)}}
  .theme-btn{{
    background:rgba(0,0,0,.06);border:1px solid rgba(0,0,0,.1);
    color:#1d1d1f;font-size:.85rem;padding:.4rem .7rem
  }}
  .theme-btn:hover{{background:rgba(0,0,0,.1)}}
  .harvest-btn{{
    background:rgba(0,125,250,.1);border:1px solid rgba(0,125,250,.25);
    color:#0071e3
  }}
  .harvest-btn:hover{{background:rgba(0,125,250,.18)}}
  /* ── Modal ── */
  .modal-backdrop{{
    display:none;position:fixed;inset:0;background:rgba(0,0,0,.35);
    z-index:200;align-items:center;justify-content:center;backdrop-filter:blur(4px)
  }}
  .modal-backdrop.open{{display:flex}}
  .modal{{
    background:#fff;border-radius:22px;padding:2rem 1.75rem 1.5rem;
    max-width:360px;width:90%;box-shadow:0 24px 80px rgba(0,0,0,.2);
    animation:modal-in .2s ease
  }}
  @keyframes modal-in{{from{{transform:scale(.94);opacity:0}}to{{transform:scale(1);opacity:1}}}}
  .modal-icon{{font-size:2rem;margin-bottom:.75rem;text-align:center}}
  .modal-title{{font-size:1.1rem;font-weight:700;color:#1d1d1f;margin-bottom:.5rem;text-align:center}}
  .modal-body{{font-size:.8rem;color:#515154;line-height:1.65;margin-bottom:1.25rem;text-align:center}}
  .modal-steps{{
    background:#f5f5f7;border-radius:12px;padding:.875rem 1rem;
    margin-bottom:1.25rem;list-style:none;display:flex;flex-direction:column;gap:.45rem
  }}
  .modal-steps li{{font-size:.78rem;color:#1d1d1f;display:flex;align-items:flex-start;gap:.5rem}}
  .modal-steps li::before{{content:"";width:6px;height:6px;border-radius:50%;
    background:#0071e3;flex-shrink:0;margin-top:.35rem}}
  .modal-actions{{display:flex;gap:.625rem;justify-content:flex-end}}
  .modal-cancel{{
    padding:.5rem 1rem;border-radius:10px;border:1px solid rgba(0,0,0,.15);
    background:transparent;color:#515154;font-size:.8rem;font-weight:600;cursor:pointer
  }}
  .modal-confirm{{
    padding:.5rem 1.25rem;border-radius:10px;border:none;
    background:#0071e3;color:#fff;font-size:.8rem;font-weight:600;cursor:pointer;
    transition:background .15s
  }}
  .modal-confirm:hover{{background:#0077ed}}
  .modal-confirm-full{{background:#636366;}}
  .modal-confirm-full:hover{{background:#48484a}}
  .staging-btn{{
    border-radius:10px;padding:.4rem 1rem;
    font-size:.8rem;font-weight:600;cursor:pointer;transition:all .15s;
    white-space:nowrap;
    background:rgba(255,149,0,.12);border:1px solid rgba(255,149,0,.3);
    color:#c47800;display:none
  }}
  .staging-btn:hover{{background:rgba(255,149,0,.22)}}
  body.dark .staging-btn{{background:rgba(255,149,0,.2);border-color:rgba(255,149,0,.4);color:#ffcc00}}
  /* ── Staging modal ── */
  .staging-modal{{max-width:520px;padding:1.75rem 1.75rem 1.5rem;max-height:85vh;overflow-y:auto}}
  .staging-file-list{{display:flex;flex-direction:column;gap:.625rem;margin:1rem 0}}
  .staging-file-item{{
    background:#f5f5f7;border-radius:12px;padding:.875rem 1rem;
    border:1px solid rgba(0,0,0,.06);cursor:pointer;transition:background .15s
  }}
  .staging-file-item:hover{{background:#ebebeb}}
  .staging-file-item.selected{{background:rgba(0,113,227,.08);border-color:rgba(0,113,227,.25)}}
  .staging-file-name{{font-size:.8rem;font-weight:700;color:#1d1d1f;margin-bottom:.2rem}}
  .staging-file-target{{font-size:.72rem;color:#86868b;font-family:ui-monospace,monospace}}
  .staging-actions{{display:flex;gap:.5rem;justify-content:flex-end;margin-top:1rem;flex-wrap:wrap}}
  .staging-apply-all{{
    padding:.55rem 1.25rem;border-radius:10px;border:none;
    background:#0071e3;color:#fff;font-size:.8rem;font-weight:600;cursor:pointer
  }}
  .staging-apply-all:hover{{background:#0077ed}}
  .staging-skip{{
    padding:.55rem 1rem;border-radius:10px;border:1px solid rgba(0,0,0,.15);
    background:transparent;color:#515154;font-size:.8rem;font-weight:600;cursor:pointer
  }}
  body.dark .staging-file-item{{background:#2c2c2e;border-color:rgba(255,255,255,.08)}}
  body.dark .staging-file-item:hover{{background:#3a3a3c}}
  body.dark .staging-file-item.selected{{background:rgba(0,113,227,.18)}}
  body.dark .staging-file-name{{color:#f5f5f7}}
  body.dark .staging-skip{{border-color:rgba(255,255,255,.15);color:#aeaeb2}}
  /* ── Progress modal ── */
  .progress-modal{{max-width:420px;padding:1.75rem 1.75rem 1.5rem}}
  .progress-modal .modal-icon{{font-size:1.75rem}}
  .progress-title{{font-size:1rem;font-weight:700;color:#1d1d1f;margin-bottom:1rem;text-align:center}}
  .progress-bar-wrap{{background:#f0f0f0;border-radius:999px;height:6px;overflow:hidden;margin-bottom:.875rem}}
  .progress-bar-fill{{height:100%;border-radius:999px;background:#0071e3;width:0%;transition:width .4s ease}}
  .progress-log{{
    height:120px;overflow-y:auto;font-size:.72rem;font-family:ui-monospace,monospace;
    color:#515154;background:#f5f5f7;border-radius:10px;padding:.625rem .75rem;
    line-height:1.55;white-space:pre-wrap;word-break:break-all
  }}
  .progress-done-btn{{
    margin-top:1rem;width:100%;padding:.55rem 1rem;border-radius:10px;border:none;
    background:#0071e3;color:#fff;font-size:.8rem;font-weight:600;cursor:pointer;
    display:none;transition:background .15s
  }}
  .progress-done-btn:hover{{background:#0077ed}}
  body.dark .progress-title{{color:#f5f5f7}}
  body.dark .progress-bar-wrap{{background:rgba(255,255,255,.1)}}
  body.dark .progress-log{{background:#1c1c1e;color:#8e8e93}}
  /* ── Dark theme ── */
  body.dark{{background:#1c1c1e;color:#f5f5f7}}
  body.dark .brand{{color:#f5f5f7}}
  body.dark .slogan{{color:#8e8e93}}
  body.dark .greeting{{color:#f5f5f7}}
  body.dark .lang-btn,.dark .theme-btn{{
    background:rgba(255,255,255,.08);border-color:rgba(255,255,255,.12);color:#f5f5f7
  }}
  body.dark .lang-btn:hover,.dark .theme-btn:hover{{background:rgba(255,255,255,.14)}}
  body.dark .harvest-btn{{background:rgba(0,125,250,.2);border-color:rgba(0,125,250,.4)}}
  body.dark .card{{background:#2c2c2e;border-color:rgba(255,255,255,.08);
    box-shadow:0 2px 12px rgba(0,0,0,.35)}}
  body.dark .card:hover{{box-shadow:0 4px 20px rgba(0,0,0,.5)}}
  body.dark .dim-label{{color:#8e8e93}}
  body.dark .ring-bg{{stroke:rgba(255,255,255,.1)}}
  body.dark .ring-score{{color:#f5f5f7}}
  body.dark .dim-suggestion{{color:#8e8e93}}
  body.dark .legend{{background:#2c2c2e;border-color:rgba(255,255,255,.08)}}
  body.dark .legend-title{{color:#8e8e93}}
  body.dark .legend-text{{color:#f5f5f7}}
  body.dark .overall-ring-bg{{stroke:rgba(255,255,255,.1)}}
  body.dark .overall-ring-num{{color:rgba(255,255,255,.6)}}
  body.dark .overall-info h2{{color:#8e8e93}}
  body.dark .overall-status{{color:#ebebf0}}
  body.dark .overall-count{{color:#8e8e93}}
  body.dark .overall-date{{color:#636366}}
  body.dark footer{{color:#636366}}
  body.dark .chat-panel{{background:#2c2c2e;border-color:rgba(255,255,255,.1)}}
  body.dark .chat-header{{border-bottom-color:rgba(255,255,255,.08)}}
  body.dark .chat-header-title{{color:#f5f5f7}}
  body.dark .chat-header-sub{{color:#8e8e93}}
  body.dark .chat-messages{{scrollbar-color:rgba(255,255,255,.1) transparent}}
  body.dark .msg-ai{{background:rgba(255,255,255,.07);color:#ebebf0}}
  body.dark .msg-user{{background:#0071e3}}
  body.dark .chat-input{{background:#1c1c1e;border-color:rgba(255,255,255,.12);color:#f5f5f7}}
  body.dark .chat-input:focus{{border-color:#0071e3;background:#1c1c1e}}
  body.dark .chat-input-row{{border-top-color:rgba(255,255,255,.08)}}
  body.dark .modal{{background:#2c2c2e}}
  body.dark .modal-title{{color:#f5f5f7}}
  body.dark .modal-body{{color:#aeaeb2}}
  body.dark .modal-steps{{background:#1c1c1e}}
  body.dark .modal-steps li{{color:#f5f5f7}}
  body.dark .modal-cancel{{border-color:rgba(255,255,255,.15);color:#aeaeb2}}
  /* ── Dim detail modal ── */
  .dim-modal{{max-width:320px}}
  .dim-modal-score{{
    font-size:3.5rem;font-weight:200;letter-spacing:-.04em;line-height:1;
    margin:.25rem 0 .125rem;text-align:center
  }}
  .dim-modal-status{{font-size:.8rem;font-weight:600;text-align:center;margin-bottom:1rem}}
  .dim-modal-sugg{{
    font-size:.82rem;color:#515154;line-height:1.65;
    background:#f5f5f7;border-radius:12px;padding:.875rem 1rem;margin-bottom:1rem
  }}
  body.dark .dim-modal-sugg{{background:#1c1c1e;color:#aeaeb2}}
  .dim-modal-chat{{
    width:100%;padding:.55rem 1rem;border-radius:10px;border:none;
    background:#0071e3;color:#fff;font-size:.8rem;font-weight:600;
    cursor:pointer;transition:background .15s
  }}
  .dim-modal-chat:hover{{background:#0077ed}}
  .card{{cursor:pointer}}
  /* ── Hero ── */
  .hero{{display:flex;align-items:center;margin-bottom:1.75rem;gap:0}}
  .hero-greeting{{flex:1;display:flex;justify-content:flex-end;padding-right:2.5rem}}
  .hero-overall{{flex:1;display:flex;justify-content:flex-start;padding-left:2.5rem}}
  /* ── Overall ring ── */
  .overall{{display:flex;flex-direction:column;align-items:center;gap:.75rem;flex-shrink:0}}
  .overall-ring-wrap{{position:relative;width:160px;height:160px}}
  .overall-ring{{transform:rotate(-90deg)}}
  .overall-ring-bg{{fill:none;stroke:rgba(0,0,0,.07);stroke-width:8}}
  .overall-ring-fill{{fill:none;stroke-width:8;stroke-linecap:round}}
  .overall-ring-score{{
    position:absolute;inset:0;display:flex;flex-direction:column;
    align-items:center;justify-content:center
  }}
  .overall-ring-num{{font-size:2.25rem;font-weight:300;line-height:1;
    color:rgba(0,0,0,.55);letter-spacing:-.02em;font-variant-numeric:tabular-nums}}
  .overall-ring-label{{display:none}}
  .overall-info{{text-align:center}}
  .overall-info h2{{font-size:.75rem;font-weight:500;color:#86868b;margin-bottom:.2rem;text-transform:uppercase;letter-spacing:.08em}}
  .overall-status{{font-size:.85rem;font-weight:500;color:#515154;margin-bottom:.15rem}}
  .overall-count{{font-size:.7rem;color:#86868b}}
  .overall-date{{font-size:.65rem;color:#aeaeb2;margin-top:.3rem}}
  /* ── Cards ── */
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:1rem}}
  .card{{
    background:#fff;border:1px solid rgba(0,0,0,.08);
    border-radius:18px;padding:1.25rem 1.25rem 1rem;
    box-shadow:0 2px 12px rgba(0,0,0,.06);
    transition:box-shadow .2s,transform .2s
  }}
  .card:hover{{box-shadow:0 4px 20px rgba(0,0,0,.1);transform:translateY(-1px)}}
  .card-header{{margin-bottom:.75rem}}
  .dim-label{{font-size:.68rem;font-weight:600;color:#86868b;text-transform:uppercase;letter-spacing:.08em}}
  /* Ring (cards) */
  .ring-wrap{{position:relative;width:72px;height:72px;margin:0 auto .75rem}}
  .ring{{transform:rotate(-90deg)}}
  .ring-bg{{fill:none;stroke:rgba(0,0,0,.07);stroke-width:5}}
  .ring-fill{{fill:none;stroke-width:5;stroke-linecap:round}}
  .ring-score{{
    position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
    font-size:1.25rem;font-weight:600;color:#1d1d1f;letter-spacing:-.03em
  }}
  .dim-status{{font-size:.72rem;font-weight:600;margin-bottom:.4rem;text-align:center}}
  .dim-suggestion{{font-size:.7rem;color:#86868b;line-height:1.5;text-align:center}}
  .sparkline{{display:block;margin-top:.625rem;opacity:.6}}
  /* Legend */
  .legend{{
    background:#fff;border:1px solid rgba(0,0,0,.08);
    border-radius:14px;padding:1.125rem 1.5rem;margin-top:1.25rem;
    display:flex;align-items:center;gap:1.5rem;flex-wrap:wrap;
    box-shadow:0 1px 6px rgba(0,0,0,.04)
  }}
  .legend-title{{font-size:.7rem;font-weight:600;color:#86868b;
    text-transform:uppercase;letter-spacing:.08em;margin-right:.25rem}}
  .legend-item{{display:flex;align-items:center;gap:.45rem}}
  .legend-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
  .legend-text{{font-size:.75rem;color:#1d1d1f;font-weight:500}}
  .legend-range{{font-size:.68rem;color:#86868b;margin-left:.1rem}}
  footer{{margin-top:1.5rem;color:#aeaeb2;font-size:.7rem;text-align:center}}
  a{{color:#0071e3;text-decoration:none}}
  /* ── Chat panel ── */
  .chat-panel{{
    position:fixed;right:1.5rem;bottom:1.5rem;
    width:320px;height:520px;
    background:#fff;border:1px solid rgba(0,0,0,.1);border-radius:20px;
    box-shadow:0 8px 40px rgba(0,0,0,.12);
    display:flex;flex-direction:column;overflow:hidden;
    z-index:100;transition:height .25s cubic-bezier(.4,0,.2,1)
  }}
  .chat-panel.collapsed{{height:52px}}
  .chat-header{{
    padding:.875rem 1.125rem;border-bottom:1px solid rgba(0,0,0,.07);
    display:flex;align-items:center;gap:.625rem;flex-shrink:0;
    cursor:pointer;user-select:none
  }}
  .chat-panel.collapsed .chat-header{{border-bottom-color:transparent}}
  .chat-header-dot{{width:8px;height:8px;border-radius:50%;background:#0071e3;flex-shrink:0}}
  .chat-header-title{{font-size:.8rem;font-weight:600;color:#1d1d1f}}
  .chat-header-sub{{font-size:.68rem;color:#86868b;margin-left:auto}}
  .chat-collapse-btn{{
    width:18px;height:18px;border-radius:50%;border:none;
    background:rgba(0,0,0,.06);color:#86868b;
    font-size:.65rem;cursor:pointer;flex-shrink:0;
    display:flex;align-items:center;justify-content:center;
    transition:transform .2s,background .15s;line-height:1
  }}
  .chat-collapse-btn:hover{{background:rgba(0,0,0,.12)}}
  .chat-panel.collapsed .chat-collapse-btn{{transform:rotate(180deg)}}
  .chat-messages{{
    flex:1;overflow-y:auto;padding:.875rem 1rem;
    display:flex;flex-direction:column;gap:.625rem;
    scroll-behavior:smooth
  }}
  .chat-messages::-webkit-scrollbar{{width:4px}}
  .chat-messages::-webkit-scrollbar-thumb{{background:rgba(0,0,0,.1);border-radius:2px}}
  .msg{{max-width:88%;padding:.55rem .8rem;border-radius:14px;font-size:.8rem;line-height:1.5;word-break:break-word}}
  .msg-user{{
    align-self:flex-end;background:#0071e3;color:#fff;
    border-bottom-right-radius:4px
  }}
  .msg-ai{{
    align-self:flex-start;background:#f5f5f7;color:#1d1d1f;
    border-bottom-left-radius:4px
  }}
  .msg-ai.thinking{{color:#86868b;font-style:italic}}
  .chat-input-row{{
    padding:.75rem;border-top:1px solid rgba(0,0,0,.07);
    display:flex;gap:.5rem;flex-shrink:0
  }}
  .chat-input{{
    flex:1;border:1px solid rgba(0,0,0,.12);border-radius:10px;
    padding:.5rem .75rem;font-size:.8rem;font-family:inherit;
    outline:none;resize:none;background:#f5f5f7;color:#1d1d1f;
    line-height:1.4;max-height:80px;overflow-y:auto
  }}
  .chat-input:focus{{border-color:#0071e3;background:#fff}}
  .chat-send{{
    background:#0071e3;color:#fff;border:none;border-radius:10px;
    width:34px;height:34px;cursor:pointer;flex-shrink:0;
    display:flex;align-items:center;justify-content:center;
    font-size:1rem;transition:background .15s;align-self:flex-end
  }}
  .chat-send:hover{{background:#0077ed}}
  .chat-send:disabled{{background:#aeaeb2;cursor:not-allowed}}
  @media(max-width:900px){{
    .chat-panel{{right:.75rem;width:280px}}
  }}
</style>
{selfos_style}
{library_style}
</head>
<body>
<div class="header">
  <div class="header-left">
    <div class="brand">SelfOS</div>
    <div class="slogan" data-zh="用简单的方式，管理你的人生"
         data-en="A simpler way to manage your life">用简单的方式，管理你的人生</div>
  </div>
  <div class="header-right">
    <div class="header-btns">
      <button class="staging-btn" onclick="openStagingModal()" id="staging-btn"
              data-zh="● 待审核" data-en="● Pending"></button>
      <button class="harvest-btn" onclick="confirmHarvest(false, true)" id="knowledge-btn"
              title="整理本地对话并直接写入知识库，保留备份与来源"
              data-zh="一键整理知识库" data-en="Build Knowledge">一键整理知识库</button>
      <button class="harvest-btn" onclick="openHarvestModal()" id="harvest-btn"
              data-zh="⟳ 采集数据" data-en="⟳ Harvest">⟳ 采集数据</button>
      {knowledge_controls}
      <button class="theme-btn" id="theme-toggle" onclick="toggleTheme()" title="切换主题">☀</button>
      <button class="lang-btn" id="lang-toggle" onclick="toggleLang()">EN</button>
    </div>
  </div>
</div>

{knowledge_overview}
{library_html}
<!-- Harvest modal -->
<div class="modal-backdrop" id="harvest-modal">
  <div class="modal">
    <div class="modal-icon">🔍</div>
    <div class="modal-title" data-zh="采集数据" data-en="Harvest Data">采集数据</div>
    <div class="modal-body"
         data-zh="将扫描你的所有 Claude Code 和 Codex 历史，通过 AI 自动分类整理，更新你的评分与 vault 内容。"
         data-en="Scan all your Claude Code and Codex history, classify it with AI, and update your scores and vault.">
      将扫描你的所有 Claude Code 和 Codex 历史，通过 AI 自动分类整理，更新你的评分与 vault 内容。
    </div>
    <ul class="modal-steps">
      <li data-zh="扫描 Claude Code 会话记录" data-en="Scan Claude Code session files">扫描 Claude Code 会话记录</li>
      <li data-zh="扫描 Codex 工作区历史" data-en="Scan Codex workspace history">扫描 Codex 工作区历史</li>
      <li data-zh="AI 分类并评估 7 个维度" data-en="AI classifies and scores 7 dimensions">AI 分类并评估 7 个维度</li>
      <li data-zh="生成最新 dashboard" data-en="Generate updated dashboard">生成最新 dashboard</li>
    </ul>
    <div class="modal-actions">
      <button class="modal-cancel" onclick="closeHarvestModal()"
              data-zh="取消" data-en="Cancel">取消</button>
      <button class="modal-confirm modal-confirm-incr" onclick="confirmHarvest(false)"
              data-zh="增量采集" data-en="Incremental">增量采集</button>
      <button class="modal-confirm modal-confirm-full" onclick="confirmHarvest(true)"
              data-zh="全量重新采集" data-en="Full Re-scan">全量重新采集</button>
    </div>
  </div>
</div>

<!-- Staging review modal -->
<div class="modal-backdrop" id="staging-modal">
  <div class="modal staging-modal">
    <div class="modal-icon">📋</div>
    <div class="modal-title" id="staging-modal-title"
         data-zh="待审核更新" data-en="Pending Updates">待审核更新</div>
    <div class="modal-body" id="staging-modal-body"
         data-zh="以下 vault 文件更新由 AI 自动生成，请确认后应用。"
         data-en="The following vault updates were auto-generated by AI. Review and apply.">
      以下 vault 文件更新由 AI 自动生成，请确认后应用。</div>
    <div class="staging-file-list" id="staging-file-list"></div>
    <div class="staging-actions">
      <button class="staging-skip" onclick="closeStagingModal()"
              data-zh="稍后再说" data-en="Later">稍后再说</button>
      <button class="staging-apply-all" onclick="applySelectedStaging()"
              id="staging-apply-btn"
              data-zh="应用选中" data-en="Apply Selected">应用选中</button>
    </div>
  </div>
</div>

<!-- Progress modal -->
<div class="modal-backdrop" id="progress-modal">
  <div class="modal progress-modal">
    <div class="modal-icon" id="progress-icon">⏳</div>
    <div class="progress-title" id="progress-title" data-zh="采集中…" data-en="Harvesting…">采集中…</div>
    <div class="progress-bar-wrap"><div class="progress-bar-fill" id="progress-bar"></div></div>
    <div class="progress-log" id="progress-log"></div>
    <button class="progress-done-btn" id="knowledge-stop-btn" onclick="stopKnowledge()" style="display:none">停止整理 / Stop</button>
    <button class="progress-done-btn" id="progress-done-btn" onclick="location.reload()"
            data-zh="完成，刷新页面" data-en="Done, Refresh">完成，刷新页面</button>
  </div>
</div>

<!-- Dimension detail modal -->
<div class="modal-backdrop" id="dim-modal">
  <div class="modal dim-modal">
    <div class="modal-icon" id="dim-modal-icon">📊</div>
    <div class="modal-title" id="dim-modal-title">—</div>
    <div class="dim-modal-score" id="dim-modal-score">—</div>
    <div class="dim-modal-status" id="dim-modal-status">—</div>
    <div class="dim-modal-sugg" id="dim-modal-sugg">—</div>
    <button class="dim-modal-chat" onclick="chatAboutDim()"
            data-zh="和 AI 聊这个维度" data-en="Chat about this">和 AI 聊这个维度</button>
  </div>
</div>

<div class="hero">
  <div class="hero-greeting">
    <div class="greeting" id="greeting-text"
         data-zh="{greeting_zh}" data-en="{greeting_en}">{greeting_zh}</div>
  </div>
  <div class="hero-overall">
    <div class="overall">
      <div class="overall-ring-wrap">
        <svg class="overall-ring" viewBox="0 0 160 160" width="160" height="160">
          <circle class="overall-ring-bg" cx="80" cy="80" r="{r_big}"/>
          <circle class="overall-ring-fill" cx="80" cy="80" r="{r_big}"
            stroke="{overall_color}"
            stroke-dasharray="{arc_big} {circ_big}"
            stroke-dashoffset="0"/>
        </svg>
        <div class="overall-ring-score">
          <span class="overall-ring-num">{overall_display}</span>
          <span class="overall-ring-label" data-zh="综合" data-en="overall">综合</span>
        </div>
      </div>
      <div class="overall-info">
        <h2 id="overall-title" data-zh="综合状态" data-en="Overall">综合状态</h2>
        <p class="overall-status" id="overall-status"
           data-zh="{overall_status_zh}" data-en="{overall_status_en}">{overall_status_zh}</p>
        <p class="overall-count" id="overall-count"
           data-zh="{scored_count} 个维度有数据"
           data-en="{scored_count} dimensions scored">{scored_count} 个维度有数据</p>
        <p class="overall-date" id="overall-date"
           data-zh="更新于 {updated}" data-en="Updated {updated}">更新于 {updated}</p>
      </div>
    </div>
  </div>
</div>

<div class="grid">{cards_html}
</div>

<div class="legend">
  <span class="legend-title" data-zh="评分说明" data-en="Scale">评分说明</span>
  <div class="legend-item">
    <div class="legend-dot" style="background:#ef4444"></div>
    <span class="legend-text" data-zh="较差" data-en="Poor">较差</span>
    <span class="legend-range">1–3</span>
  </div>
  <div class="legend-item">
    <div class="legend-dot" style="background:#f97316"></div>
    <span class="legend-text" data-zh="需关注" data-en="Watch">需关注</span>
    <span class="legend-range">4–5</span>
  </div>
  <div class="legend-item">
    <div class="legend-dot" style="background:#eab308"></div>
    <span class="legend-text" data-zh="一般" data-en="OK">一般</span>
    <span class="legend-range">6–7</span>
  </div>
  <div class="legend-item">
    <div class="legend-dot" style="background:#22c55e"></div>
    <span class="legend-text" data-zh="良好" data-en="Great">良好</span>
    <span class="legend-range">8–10</span>
  </div>
</div>

<footer>SelfOS · <span data-zh="数据来源" data-en="Source">数据来源</span>: vault/ ·
<a href="vault/90_Inbox/"><span data-zh="查看原始摘要" data-en="View digest">查看原始摘要</span></a></footer>

<!-- Chat panel -->
<div class="chat-panel collapsed" id="chat-panel">
  <div class="chat-header" onclick="toggleChat()">
    <div class="chat-header-dot"></div>
    <span class="chat-header-title" data-zh="和我聊聊" data-en="Let's talk">和我聊聊</span>
    <span class="chat-header-sub" data-zh="基于你的知识库" data-en="from your knowledge">基于你的知识库</span>
    <button class="chat-collapse-btn" id="chat-collapse-btn" onclick="toggleChat(event)" aria-expanded="false" aria-label="展开聊天">▼</button>
  </div>
  <div class="chat-messages" id="chat-messages">
    <div class="msg msg-ai" data-zh="你好。想梳理一个项目，还是聊聊最近的想法？"
         data-en="Hi. Want to think through a project, or talk about what's on your mind?">你好。想梳理一个项目，还是聊聊最近的想法？</div>
  </div>
  <div class="chat-input-row">
    <textarea class="chat-input" id="chat-input" rows="1"
      placeholder="输入消息…" data-ph-zh="输入消息…" data-ph-en="Type a message…"></textarea>
    <button class="chat-send" id="chat-send" onclick="sendChat()">↑</button>
  </div>
</div>

<script>
// ── Theme ──
let isDark = localStorage.getItem('selfos-theme') === 'dark';
(function() {{
  if (isDark) document.body.classList.add('dark');
  updateThemeBtn();
}})();
function updateThemeBtn() {{
  document.getElementById('theme-toggle').textContent = isDark ? '🌙' : '☀';
}}
function toggleTheme() {{
  isDark = !isDark;
  document.body.classList.toggle('dark', isDark);
  localStorage.setItem('selfos-theme', isDark ? 'dark' : 'light');
  updateThemeBtn();
}}

// ── Language ──
let lang = localStorage.getItem('selfos-lang') === 'zh' ? 'zh' : 'en';
document.documentElement.lang = lang;
function applyLanguage() {{
  document.getElementById('lang-toggle').textContent = lang === 'zh' ? 'EN' : '中文';
  document.documentElement.lang = lang;
  localStorage.setItem('selfos-lang', lang);
  document.dispatchEvent(new Event('selfos-language'));
  updateKnowledgeOverview();
  document.querySelectorAll('[data-zh][data-en]').forEach(el => {{
    el.textContent = el.dataset[lang];
  }});
  const inp = document.getElementById('chat-input');
  inp.placeholder = lang === 'zh' ? '输入消息…' : 'Type a message…';
}}
function toggleLang() {{
  lang = lang === 'zh' ? 'en' : 'zh';
  applyLanguage();
}}
document.addEventListener('DOMContentLoaded', applyLanguage);

// ── Dim icons ──
const DIM_ICONS = {{
  career:'💼', work:'🛠', health:'💪', learning:'📚',
  research:'🔬', life:'🌿', family:'🏠'
}};
let _currentDimKey = '';
let _pendingDimMsg = '';

function chatAboutDim() {{
  document.getElementById('dim-modal').classList.remove('open');
  if (chatCollapsed) toggleChat();
  _sendChatSilent(_pendingDimMsg);
}}

function openDim(card) {{
  const key   = card.dataset.key;
  const score = card.dataset.score;
  const color = card.dataset.color;
  _currentDimKey = key;
  const label = card.dataset[lang === 'zh' ? 'labelZh' : 'labelEn'];

  // Show modal
  document.getElementById('dim-modal-icon').textContent  = DIM_ICONS[key] || '📊';
  document.getElementById('dim-modal-title').textContent = label;
  const scoreEl = document.getElementById('dim-modal-score');
  scoreEl.textContent = score;
  scoreEl.style.color = color;
  document.getElementById('dim-modal-status').textContent = card.dataset[lang === 'zh' ? 'statusZh' : 'statusEn'];
  document.getElementById('dim-modal-status').style.color = color;
  document.getElementById('dim-modal-sugg').textContent   = card.dataset[lang === 'zh' ? 'suggZh' : 'suggEn'];
  document.getElementById('dim-modal').classList.add('open');

  // Pre-store the message so the chat button can send it
  _pendingDimMsg = lang === 'zh' ? `帮我分析一下「${{label}}」这个维度` : `Tell me about my ${{label}} dimension`;
}}
document.getElementById('dim-modal').addEventListener('click', e => {{
  if (e.target === e.currentTarget) document.getElementById('dim-modal').classList.remove('open');
}});

// Send a chat message without touching the input box
async function _sendChatSilent(text) {{
  appendMsg(text, 'user');
  chatHistory.push({{role:'user', content: text}});
  const thinking = appendMsg(lang === 'zh' ? '思考中…' : 'Thinking…', 'ai');
  thinking.classList.add('thinking');
  try {{
    const fetchPromise = fetch('/chat', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{messages: chatHistory}})
    }});
    const res = await fetchPromise;
    const data = await res.json();
    thinking.remove();
    const reply = data.reply || data.error || 'Error';
    appendMsg(reply, 'ai');
    chatHistory.push({{role:'assistant', content: reply}});
  }} catch(e) {{
    thinking.textContent = lang === 'zh' ? '连接失败，请启动 serve.py' : 'Connection failed — run serve.py';
  }}
}}

// ── Harvest modal ──
function openHarvestModal() {{
  document.getElementById('harvest-modal').classList.add('open');
}}
function closeHarvestModal() {{
  document.getElementById('harvest-modal').classList.remove('open');
}}
let importRunning = false;
let knowledgeRecoveryGeneration = 0;
function recoverKnowledgeRun() {{
  const generation = ++knowledgeRecoveryGeneration;
  importRunning = true;
  const bar = document.getElementById('progress-bar');
  const stopBtn = document.getElementById('knowledge-stop-btn');
  const title = document.getElementById('progress-title');
  const icon = document.getElementById('progress-icon');
  const doneBtn = document.getElementById('progress-done-btn');
  document.getElementById('progress-modal').classList.add('open');
  doneBtn.style.display = 'none';
  stopBtn.style.display = 'block';
  stopBtn.disabled = false;
  title.textContent = lang === 'zh' ? '正在核实整理任务状态…' : 'Checking knowledge task status…';
  async function recover() {{
    try {{
      const response = await fetch('/__knowledge_run__', {{cache: 'no-store'}});
      if (!response.ok) throw new Error('Status unavailable');
      const state = await response.json();
      if (generation !== knowledgeRecoveryGeneration) return;
      if (state.total) bar.style.width = Math.max(parseFloat(bar.style.width) || 0,
        10 + Math.round(80 * state.completed / state.total)) + '%';
      if (state.running) {{
        title.textContent = state.phase === 'stopping'
          ? (lang === 'zh' ? '正在停止并保存进度…' : 'Stopping and saving progress…')
          : (lang === 'zh' ? '整理任务仍在运行，正在同步状态…' : 'Task is running; syncing status…');
        setTimeout(recover, 1500);
        return;
      }}
      const result = state.result || {{ok: false}};
      importRunning = false;
      stopBtn.style.display = 'none';
      if (result.ok && !result.cancelled) bar.style.width = '100%';
      icon.textContent = result.ok && !result.cancelled ? '✅' : '⚠️';
      title.textContent = result.cancelled
        ? (lang === 'zh' ? '已停止，已保存进度，可继续整理' : 'Stopped; progress saved, resume available')
        : result.ok ? (lang === 'zh' ? '知识库整理完成' : 'Knowledge complete')
        : (lang === 'zh' ? '整理未完成，可重试' : 'Incomplete; retry available');
      doneBtn.style.display = 'block';
      doneBtn.textContent = lang === 'zh' ? '完成，刷新页面' : 'Done, Refresh';
      checkStaging();
    }} catch (error) {{
      if (generation !== knowledgeRecoveryGeneration) return;
      title.textContent = lang === 'zh' ? '暂时无法连接服务，正在重试状态查询…' : 'Server unavailable; retrying status…';
      setTimeout(recover, 2000);
    }}
  }}
  recover();
}}
// A reload attaches to a live task without launching an import.
fetch('/__knowledge_run__', {{cache: 'no-store'}}).then(response => response.ok ? response.json() : null)
  .then(state => {{ if (state && state.running && !importRunning) recoverKnowledgeRun(); }}).catch(() => {{}});
async function stopKnowledge() {{
  const btn = document.getElementById('knowledge-stop-btn');
  btn.disabled = true;
  try {{
    const response = await fetch('/__knowledge_stop__', {{method: 'POST'}});
    if (!response.ok) throw new Error('Stop request failed');
    document.getElementById('progress-title').textContent = lang === 'zh'
      ? '正在停止，保存已完成结果…' : 'Stopping; saving completed results…';
  }} catch (error) {{
    btn.disabled = false;
    document.getElementById('progress-log').textContent += String.fromCharCode(10) + error.message;
  }}
}}

function confirmHarvest(full, knowledge = false, rebuild = false) {{
  if (importRunning) return;
  ++knowledgeRecoveryGeneration;
  importRunning = true;
  const stopBtn = document.getElementById('knowledge-stop-btn');
  stopBtn.disabled = false;
  stopBtn.style.display = knowledge ? 'block' : 'none';
  closeHarvestModal();
  // show progress modal
  const pm = document.getElementById('progress-modal');
  const bar = document.getElementById('progress-bar');
  const log = document.getElementById('progress-log');
  const icon = document.getElementById('progress-icon');
  const title = document.getElementById('progress-title');
  const doneBtn = document.getElementById('progress-done-btn');
  bar.style.width = '0%';
  log.textContent = '';
  icon.textContent = '⏳';
  title.textContent = knowledge
    ? (lang === 'zh' ? '正在整理知识库…' : 'Building knowledge…')
    : (lang === 'zh' ? '采集中…' : 'Harvesting…');
  doneBtn.style.display = 'none';
  pm.classList.add('open');

  // progress steps map keywords → approximate % complete
  const STEPS = [
    ['SelfOS Harvest', 5],
    ['Extracting', 20],
    ['extraction', 30],
    ['build_session', 50],
    ['digest', 60],
    ['Scoring', 75],
    ['Dashboard', 88],
    ['Done', 100],
  ];
  let pct = 0;
  const savedSessions = new Set();
  function advanceTo(n) {{
    if (n > pct) {{ pct = n; bar.style.width = pct + '%'; }}
  }}

  const url = knowledge ? '/__knowledge_stream__' + (rebuild ? '?action=rebuild' : '') : '/__harvest_stream__?full=' + (full ? '1' : '0');
  const es = new EventSource(url);
  es.onmessage = function(e) {{
    let msg;
    try {{ msg = JSON.parse(e.data); }} catch {{ return; }}
    if (msg.done) {{
      es.close();
      importRunning = false;
      stopBtn.style.display = 'none';
      if (msg.ok && !msg.cancelled) advanceTo(100);
      icon.textContent = msg.ok ? '✅' : '⚠️';
      title.textContent = msg.ok
        ? (lang === 'zh' ? (knowledge ? '知识库整理完成' : '采集完成') : 'Done')
        : (lang === 'zh' ? (knowledge ? '整理未完成，可重试' : '采集出错') : 'Error — retry available');
      if (msg.cancelled) title.textContent = lang === 'zh' ? '已停止，可继续整理' : 'Stopped; resume available';
      if (msg.ok) checkStaging();
      doneBtn.style.display = 'block';
      doneBtn.textContent = lang === 'zh' ? '完成，刷新页面' : 'Done, Refresh';
      return;
    }}
    const line = msg.line || '';
    if (line.trim()) {{
      log.textContent += (log.textContent ? '\\n' : '') + line;
      log.scrollTop = log.scrollHeight;
      if (knowledge) {{
        const batch = line.match(/(?:Organizing|Saved) (?:batch|session) (\\d+)\\/(\\d+)/);
        if (batch) {{
          if (line.startsWith('Saved')) savedSessions.add(batch[1]);
          const completed = savedSessions.size;
          advanceTo(10 + Math.round(80 * completed / Number(batch[2])));
        }} else if (line.includes('Knowledge:')) advanceTo(10);
      }} else {{
        for (const [kw, p] of STEPS) {{
          if (line.toLowerCase().includes(kw.toLowerCase())) {{ advanceTo(p); break; }}
        }}
      }}
    }}
  }};
  es.onerror = function() {{
    es.close();
    if (knowledge) {{
      recoverKnowledgeRun();
      return;
    }}
    importRunning = false;
    icon.textContent = '⚠️';
    title.textContent = lang === 'zh' ? '连接中断' : 'Connection lost';
    doneBtn.style.display = 'block';
  }};
}}
document.getElementById('harvest-modal').addEventListener('click', e => {{
  if (e.target === e.currentTarget) closeHarvestModal();
}});

// ── Chat collapse ──
let chatCollapsed = localStorage.getItem('selfos-chat-open') !== 'true';
document.getElementById('chat-panel').classList.toggle('collapsed', chatCollapsed);
document.getElementById('chat-collapse-btn').setAttribute('aria-expanded', String(!chatCollapsed));
function toggleChat(e) {{
  if (e) e.stopPropagation();
  chatCollapsed = !chatCollapsed;
  document.getElementById('chat-panel').classList.toggle('collapsed', chatCollapsed);
  localStorage.setItem('selfos-chat-open', String(!chatCollapsed));
  document.getElementById('chat-collapse-btn').setAttribute('aria-expanded', String(!chatCollapsed));
  document.getElementById('chat-collapse-btn').setAttribute('aria-label', chatCollapsed ? '展开聊天' : '收起聊天');
}}

// ── Chat ──
const chatHistory = [];
function appendMsg(text, role) {{
  const box = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'msg ' + (role === 'user' ? 'msg-user' : 'msg-ai');
  div.textContent = text;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  return div;
}}
async function sendChat() {{
  const inp = document.getElementById('chat-input');
  const text = inp.value.trim();
  if (!text) return;
  inp.value = '';
  inp.style.height = 'auto';
  document.getElementById('chat-send').disabled = true;

  appendMsg(text, 'user');
  chatHistory.push({{role:'user', content: text}});

  const thinking = appendMsg(lang === 'zh' ? '思考中…' : 'Thinking…', 'ai');
  thinking.classList.add('thinking');

  try {{
    const res = await fetch('/chat', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{messages: chatHistory}})
    }});
    const data = await res.json();
    thinking.remove();
    const reply = data.reply || data.error || 'Error';
    appendMsg(reply, 'ai');
    chatHistory.push({{role:'assistant', content: reply}});
  }} catch(e) {{
    thinking.textContent = lang === 'zh' ? '连接失败，请启动 serve.py' : 'Connection failed — run serve.py';
    thinking.classList.add('thinking');
  }}
  document.getElementById('chat-send').disabled = false;
  inp.focus();
}}
document.getElementById('chat-input').addEventListener('keydown', e => {{
  if (e.key === 'Enter' && !e.shiftKey) {{ e.preventDefault(); sendChat(); }}
}});
document.getElementById('chat-input').addEventListener('input', function() {{
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 80) + 'px';
}});

// Sparkline
document.querySelectorAll('.sparkline').forEach(canvas => {{
  const values = JSON.parse(canvas.dataset.values);
  const color = canvas.dataset.color;
  const ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;
  if (values.filter(v => v !== null).length < 2) return;
  ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.beginPath();
  let first = true;
  values.forEach((v, i) => {{
    if (v === null) {{ first = true; return; }}
    const x = (i / (values.length - 1)) * w;
    const y = h - ((v - 1) / 9) * (h - 4) - 2;
    if (first) {{ ctx.moveTo(x, y); first = false; }} else ctx.lineTo(x, y);
  }});
  ctx.stroke();
}});
// ── Staging review ──
let _stagingFiles = [];
function checkStaging() {{
  fetch('/__staging__').then(r => r.json()).then(data => {{
    _stagingFiles = data.files || [];
    const btn = document.getElementById('staging-btn');
    if (_stagingFiles.length > 0) {{
      btn.style.display = '';
      btn.textContent = lang === 'zh'
        ? `● ${{_stagingFiles.length}} 待审核`
        : `● ${{_stagingFiles.length}} Pending`;
    }} else {{
      btn.style.display = 'none';
    }}
  }}).catch(() => {{}});
}}
function openStagingModal() {{
  const list = document.getElementById('staging-file-list');
  list.innerHTML = '';
  _stagingFiles.forEach((f, i) => {{
    const item = document.createElement('div');
    item.className = 'staging-file-item selected';
    item.dataset.idx = i;
    item.innerHTML = `<div class="staging-file-name">${{f.name}}</div>`
      + `<div class="staging-file-target">→ ${{f.target || '(unknown target)'}}</div>`;
    item.onclick = () => item.classList.toggle('selected');
    list.appendChild(item);
  }});
  document.getElementById('staging-modal').classList.add('open');
}}
function closeStagingModal() {{
  document.getElementById('staging-modal').classList.remove('open');
}}
function applySelectedStaging() {{
  const items = document.querySelectorAll('.staging-file-item.selected');
  const filenames = Array.from(items).map(el => _stagingFiles[+el.dataset.idx].name);
  if (!filenames.length) {{ closeStagingModal(); return; }}
  const btn = document.getElementById('staging-apply-btn');
  btn.disabled = true;
  btn.textContent = lang === 'zh' ? '应用中…' : 'Applying…';
  fetch('/__staging__/apply', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{files: filenames}})
  }}).then(r => r.json()).then(data => {{
    closeStagingModal();
    checkStaging();
    btn.disabled = false;
    btn.textContent = lang === 'zh' ? '应用选中' : 'Apply Selected';
  }}).catch(() => {{
    btn.disabled = false;
    btn.textContent = lang === 'zh' ? '应用选中' : 'Apply Selected';
  }});
}}
document.getElementById('staging-modal').addEventListener('click', e => {{
  if (e.target === e.currentTarget) closeStagingModal();
}});
checkStaging();

</script>
</body>
</html>"""

    out = vault.parent / "dashboard.html"
    from selfos.web.rendering.overall import integrate_overall
    html = integrate_overall(html)
    out.write_text(html, encoding="utf-8")
    return out


STATE_FILE_NAME = ".bootstrap_state.json"
