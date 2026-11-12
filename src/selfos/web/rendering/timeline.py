"""Localized read-only project chronology, separate from persisted user history."""
from selfos.web.rendering.resources import frontend_text, render_ui
import json
from importlib.resources import files

LOCALES = {language: json.loads(files('selfos.resources').joinpath('locales', directory, 'timeline.json').read_text(encoding='utf-8'))
           for language, directory in [('en', 'en'), ('zh', 'zh-CN')]}

HTML = frontend_text('templates/project-timeline.html').replace('TIMELINE_LOCALES', json.dumps(LOCALES, ensure_ascii=True).replace('<', '\u003c'))

HTML = '<!-- selfos-project-timeline-start -->' + HTML + '<!-- selfos-project-timeline-end -->'
