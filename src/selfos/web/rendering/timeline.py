"""Localized read-only project chronology, separate from persisted user history."""
from selfos.web.rendering.resources import frontend_text, render_ui

from selfos.web.i18n import namespace_messages
LOCALES = namespace_messages('timeline')

HTML = frontend_text('templates/project-timeline.html')

HTML = '<!-- selfos-project-timeline-start -->' + HTML + '<!-- selfos-project-timeline-end -->'
