"""Publication status component with packaged locale strings."""
from selfos.web.rendering.resources import frontend_text, render_ui

from selfos.web.i18n import namespace_messages
LOCALES = namespace_messages('import')

HTML = frontend_text('templates/import-publication.html')

SCRIPT = frontend_text('scripts/import-publication.js')
