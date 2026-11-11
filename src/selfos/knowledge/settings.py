"""knowledge / settings responsibilities."""
import copy, re

DEFAULT_SETTINGS={'domains':['work','research','learning','personal','life','health'],'detail':'balanced'}


DETAILS={'concise':{'decisions':4,'characters':300,'session_chars':16000},
         'balanced':{'decisions':8,'characters':600,'session_chars':24000},
         'detailed':{'decisions':12,'characters':1200,'session_chars':24000}}


FILES={'personal_facts':'knowledge/personal_facts.md','preferences':'knowledge/preferences.md',
       'history':'knowledge/history.md'}


VERSION=3


def validate_settings(value):
    if not isinstance(value,dict) or set(value)-{'domains','detail'}:
        raise ValueError('Settings accept only domains and detail')
    value={**copy.deepcopy(DEFAULT_SETTINGS),**value}
    domains=value['domains']
    if not isinstance(domains,list) or not 1<=len(domains)<=20 or any(
        not isinstance(d,str) or not re.fullmatch(r'[A-Za-z0-9_\-\u4e00-\u9fff ]{1,40}',d) for d in domains):
        raise ValueError('Select at least one domain; domain names cannot contain paths')
    if value['detail'] not in DETAILS:
        raise ValueError('Detail must be concise, balanced or detailed')
    value['domains']=list(dict.fromkeys(d.strip().casefold() for d in domains))
    if any(not d for d in value['domains']):
        raise ValueError('Domain names must not be empty')
    return value






def policy_hash(settings):
    from selfos.knowledge.identity import digest
    return digest({'version':VERSION,'settings':validate_settings(settings)})


def limits(settings=None):
    return DETAILS[validate_settings(settings or DEFAULT_SETTINGS)['detail']]
