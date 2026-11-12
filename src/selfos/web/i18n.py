"""Validated package locale catalogs shared by server rendering and browser UI."""
import copy
import json
import re
from functools import lru_cache
from importlib.resources import files

_PARAMETER = re.compile(r'\{([A-Za-z][A-Za-z0-9_]*)\}')
_IDENTITY = re.compile(r'[A-Za-z][A-Za-z0-9-]{0,31}\Z')
_TAG = re.compile(r'(?:[A-Za-z]{2,3}|[A-Za-z]{5,8})(?:-[A-Za-z]{4})?'
                  r'(?:-[A-Za-z]{2}|-[0-9]{3})?'
                  r'(?P<variants>(?:-(?:[A-Za-z0-9]{5,8}|[0-9][A-Za-z0-9]{3}))*)'
                  r'(?:-[0-9A-WY-Za-wy-z](?:-[A-Za-z0-9]{2,8})+)*'
                  r'(?:-x(?:-[A-Za-z0-9]{1,8})+)?\Z', re.IGNORECASE)


def _valid_tag(value):
    match = _TAG.fullmatch(value)
    if not match:
        return False
    variants = match['variants'].lower().split('-')[1:]
    if len(variants) != len(set(variants)):
        return False
    extensions = []
    for part in value.lower().split('-'):
        if part == 'x':
            break
        if len(part) == 1:
            extensions.append(part)
    return len(extensions) == len(set(extensions))


def validate_catalogs(data):
    locales = data.get('locales', {})
    if data.get('default') != 'en' or 'en' not in locales:
        raise ValueError('English locale is required')
    aliases = {}
    for identity, locale in locales.items():
        if not _IDENTITY.fullmatch(identity):
            raise ValueError('Invalid locale identity')
        if any(not isinstance(locale.get(field), str) or not locale[field] for field in ('name', 'tag', 'document_tag')):
            raise ValueError('Invalid locale metadata')
        document_tag = locale['document_tag']
        valid_document = _valid_tag(document_tag) or re.fullmatch(r'x(?:-[A-Za-z0-9]{1,8})+', document_tag, re.IGNORECASE)
        if not _valid_tag(locale['tag']) or not valid_document:
            raise ValueError('Invalid locale tag')
        if not isinstance(locale.get('aliases'), list):
            raise ValueError('Invalid locale aliases')
        for alias in [identity, *locale['aliases']]:
            if not isinstance(alias, str) or not _IDENTITY.fullmatch(alias):
                raise ValueError('Invalid locale alias')
            previous = aliases.get(alias.casefold())
            if previous and previous != identity:
                raise ValueError('Duplicate locale alias')
            aliases[alias.casefold()] = identity
        if not isinstance(locale.get('messages'), dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in locale['messages'].items()):
            raise ValueError('Locale messages must be strings')
    english = locales['en']['messages']
    missing = {}
    for identity, locale in locales.items():
        extra = set(locale['messages']) - set(english)
        if extra:
            raise ValueError('Locale has unknown message keys')
        for key, value in locale['messages'].items():
            if set(_PARAMETER.findall(value)) != set(_PARAMETER.findall(english[key])):
                raise ValueError('Inconsistent translation parameters: ' + key)
        missing[identity] = sorted(set(english) - set(locale['messages']))
    return {'missing': missing, 'aliases': aliases}


def load_catalogs(root):
    locales = {}
    for folder in sorted(root.iterdir(), key=lambda item: item.name):
        if not folder.is_dir() or not folder.joinpath('meta.json').is_file():
            continue
        metadata = json.loads(folder.joinpath('meta.json').read_text(encoding='utf-8'))
        messages = {}
        for resource in sorted(folder.iterdir(), key=lambda item: item.name):
            if resource.name == 'meta.json' or not resource.name.endswith('.json') or not resource.is_file():
                continue
            namespace = resource.name[:-5]
            values = json.loads(resource.read_text(encoding='utf-8'))
            if not isinstance(values, dict):
                raise ValueError('Locale namespace must be a mapping')
            messages.update({namespace + '.' + key: value for key, value in values.items()})
        locales[folder.name] = {**metadata, 'messages': messages}
    data = {'default': 'en', 'locales': locales}
    validate_catalogs(data)
    return data


@lru_cache(maxsize=1)
def _loaded():
    return load_catalogs(files('selfos.resources').joinpath('locales'))


def catalogs():
    return copy.deepcopy(_loaded())


def namespace_messages(namespace):
    """Compatibility view of a namespace, derived from shared locale metadata."""
    prefix = namespace + "."
    return {locale["document_tag"]: {key[len(prefix):]: value
            for key, value in locale["messages"].items() if key.startswith(prefix)}
            for locale in _loaded()["locales"].values()}


def normalize_locale(value, data=None):
    data = data or _loaded()
    aliases = validate_catalogs(data)['aliases']
    return aliases.get(value.casefold(), 'en') if isinstance(value, str) else 'en'


def translate(key, locale=None, params=None, data=None):
    data = data or _loaded()
    identity = normalize_locale(locale, data)
    english = data['locales']['en']['messages']
    if key not in english:
        raise ValueError('Unknown translation key: ' + str(key))
    message = data['locales'][identity]['messages'].get(key, english[key])
    params = params or {}
    required = set(_PARAMETER.findall(message))
    if not required.issubset(params):
        raise ValueError('Missing translation parameters: ' + key)
    return _PARAMETER.sub(lambda match: str(params[match[1]]), message)


def runtime(data=None):
    from selfos.web.rendering.resources import frontend_text
    data = data or _loaded()
    validate_catalogs(data)
    encoded = json.dumps(data, ensure_ascii=True).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return frontend_text('templates/i18n.html').replace('__I18N_CATALOGS__', encoded)
