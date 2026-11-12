"""web / rendering / model responsibilities."""
from selfos.web.rendering.resources import frontend_text, render_ui


CONTROLS = frontend_text('templates/settings-model.html')

def _embed_messages():
    import json
    from importlib.resources import files
    root=files('selfos.resources').joinpath('locales')
    messages={key:json.loads(root.joinpath(locale,'model.json').read_text(encoding='utf-8'))
              for key,locale in [('en','en'),('zh','zh-CN')]}
    return json.dumps(messages,ensure_ascii=True).replace('<','\\u003c')

CONTROLS=CONTROLS.replace('__MODEL_MESSAGES__',_embed_messages())
