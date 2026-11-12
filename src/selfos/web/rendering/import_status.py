"""Publication status component with packaged locale strings."""
from selfos.web.rendering.resources import frontend_text, render_ui
import json
from importlib.resources import files

LOCALES = {language: json.loads(files('selfos.resources').joinpath(
    'locales', folder, 'import.json').read_text(encoding='utf-8'))
    for language, folder in [('en', 'en'), ('zh', 'zh-CN')]}

HTML = frontend_text('templates/import-publication.html')

SCRIPT = 'const importLocales = ' + json.dumps(LOCALES, ensure_ascii=True) + ';\n' + frontend_text('scripts/import-publication.js')
