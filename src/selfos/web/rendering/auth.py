"""web / rendering / auth responsibilities."""
from selfos.web.rendering.resources import frontend_text
import json

def resources():
    from selfos.paths import resource
    root=resource('locales')
    return {code:json.loads((root/folder/'auth.json').read_text(encoding='utf-8')) for code,folder in [('en','en'),('zh','zh-CN')]}


STYLE=frontend_text('templates/auth-style.html')


SCRIPT=frontend_text('templates/auth-script.html')


def script():return SCRIPT.replace('__LOCALES__',json.dumps(resources(),ensure_ascii=False))


def login_page():
    return frontend_text('templates/login-head.html')+STYLE+frontend_text('templates/login-form.html')+script()+frontend_text('templates/login-tail.html')


def account_controls():
    return STYLE+frontend_text('templates/account-controls.html')+script()+frontend_text('templates/account-script.html')


ACCOUNT_CONTROLS=account_controls()
