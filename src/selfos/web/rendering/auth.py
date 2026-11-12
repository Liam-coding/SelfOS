"""web / rendering / auth responsibilities."""
from selfos.web.rendering.resources import frontend_text
def resources():
    from selfos.web.i18n import catalogs
    return {locale['document_tag']: {key[5:]:value for key,value in locale['messages'].items() if key.startswith('auth.')}
            for locale in catalogs()['locales'].values()}


STYLE=frontend_text('templates/auth-style.html')


SCRIPT=frontend_text('templates/auth-script.html')


def script(include_runtime=True):
    from selfos.web.i18n import runtime
    return (runtime() if include_runtime else '')+SCRIPT


def login_page():
    return frontend_text('templates/login-head.html')+STYLE+frontend_text('templates/login-form.html')+script()+frontend_text('templates/login-tail.html')


def account_controls(include_runtime=True):
    return STYLE+frontend_text('templates/account-controls.html')+script(include_runtime)+frontend_text('templates/account-script.html')


ACCOUNT_CONTROLS=account_controls()
