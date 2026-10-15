"""Shared translations for the session service and its hosted QML pages."""
import json
import os
from pathlib import Path
import re
from functools import lru_cache

CATALOGS = Path(__file__).with_name('locales')

def language(value):
    value = (value or 'en').split('.')[0].split('@')[0].replace('-', '_')
    if value.lower().startswith('zh'):
        return 'zh_TW' if any(x in value.lower() for x in ('tw', 'hk', 'mo', 'hant')) else 'zh_CN'
    value = value.split('_')[0].lower()
    return value if value in ('en', 'de', 'fr', 'ru') else 'en'

def current_language():
    return language(next((os.environ[k] for k in ('SFOS_QUICKSHARE_LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG') if os.environ.get(k)), 'en'))

@lru_cache(maxsize=16)
def catalog(locale):
    path = CATALOGS / (language(locale) + '.json')
    if not path.is_file(): return {}
    return json.loads(path.read_text(encoding='utf8'))

def tr(message, *args, locale=None):
    text = catalog(locale or current_language()).get(message, message)
    return re.sub(r'%([1-9][0-9]*)', lambda m: str(args[int(m[1])-1]) if int(m[1]) <= len(args) else m[0], text)

def error_text(error):
    """Translate expected errors; preserve unknown protocol diagnostics verbatim."""
    text = str(error)
    if text in catalog('en'): return tr(text)
    for prefix in ('Interface has no IPv4 address: ', 'Worker exited: ',
                   'Files saved; transfer history failed: ', 'Files saved; notification failed: ',
                   'Quick Share Java runtime is missing '):
        if text.startswith(prefix): return tr(prefix + '%1', text[len(prefix):])
    return text
