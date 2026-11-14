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
    lifecycle=''.join('<script data-selfos-module="'+identity+'" data-selfos-generation="1">'+frontend_text('scripts/ui-'+identity+'.js')+'</script>' for identity in ('runtime','request','bootstrap'))
    return frontend_text('templates/login-head.html')+lifecycle+STYLE+frontend_text('templates/login-form.html')+script()+frontend_text('templates/login-tail.html')


def account_controls(include_runtime=True, include_lifecycle=True):
    start=(''.join('<script data-selfos-module="'+identity+'" data-selfos-generation="1">'+frontend_text('scripts/ui-'+identity+'.js')+'</script>' for identity in ('runtime','request'))) if include_lifecycle else ''
    end=('<script data-selfos-module="bootstrap" data-selfos-generation="1">'+frontend_text('scripts/ui-bootstrap.js')+'</script>') if include_lifecycle else ''
    return start+STYLE+frontend_text('templates/account-controls.html')+script(include_runtime)+frontend_text('templates/account-script.html')+end


ACCOUNT_CONTROLS=account_controls()
