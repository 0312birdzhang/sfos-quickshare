import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest
from unittest.mock import patch
from quickshare.i18n import catalog, current_language, error_text, language, tr

ROOT = Path(__file__).resolve().parents[1]

class TranslationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is optional for generated QML JavaScript parity checks')
    def test_generated_javascript_matches_python(self):
        cases = [(locale, key) for locale in ('en', 'zh_CN', 'zh_TW', 'de', 'fr', 'ru', 'unknown') for key in catalog('en')]
        script = """const fs=require('fs'),vm=require('vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const ctx={};vm.createContext(ctx);
vm.runInContext(fs.readFileSync('qml/QuickShareI18n.js','utf8').replace('.pragma library',''),ctx);
process.stdout.write(JSON.stringify(input.map(c=>ctx.translate(c[1],['A %2','B'],c[0]))));"""
        result = subprocess.run(['node', '-e', script], input=json.dumps(cases), capture_output=True, text=True, encoding='utf8', cwd=ROOT, check=True)
        self.assertEqual(json.loads(result.stdout), [tr(key, 'A %2', 'B', locale=locale) for locale, key in cases])

    def test_catalog_completeness_and_placeholders(self):
        base = catalog('en')
        self.assertEqual(len(base), 38)
        for locale in ('en', 'zh_CN', 'zh_TW', 'de', 'fr', 'ru'):
            entries = catalog(locale)
            self.assertEqual(entries.keys(), base.keys(), locale)
            for key, value in entries.items():
                self.assertTrue(value.strip(), (locale, key))
                self.assertEqual(sorted(re.findall(r'%\d+', key)), sorted(re.findall(r'%\d+', value)), (locale, key))

    def test_locale_normalization_and_fallback(self):
        for source, expected in [('zh-Hant-HK', 'zh_TW'), ('zh_CN.UTF-8', 'zh_CN'),
                                 ('fr_CA', 'fr'), ('de_DE@euro', 'de'), ('ru_RU', 'ru'),
                                 ('C', 'en'), ('es_ES', 'en'), ('../../etc', 'en')]:
            self.assertEqual(language(source), expected)
        self.assertEqual(tr('Reject', locale='unsupported'), 'Reject')
        self.assertEqual(tr('New diagnostic', locale='zh_CN'), 'New diagnostic')

    def test_language_environment_and_literal_substitutions(self):
        with patch.dict(os.environ, {'LANG': 'de_DE.UTF-8'}, clear=True):
            self.assertEqual(current_language(), 'de')
            self.assertEqual(tr('Reject'), 'Ablehnen')
        template = '%1: verify PIN %2 in Settings → Quick Share.'
        result = tr(template, '%2-user', '1234', locale='en')
        self.assertEqual(result, '%2-user: verify PIN 1234 in Settings → Quick Share.')

    def test_common_errors_and_diagnostics(self):
        with patch.dict(os.environ, {'SFOS_QUICKSHARE_LANGUAGE': 'zh_TW'}, clear=True):
            self.assertEqual(error_text('No local network connection'), '沒有可用的區域網路連線')
            self.assertIn('wlan0', error_text('Interface has no IPv4 address: wlan0'))
            self.assertEqual(error_text('Wire error 0x42'), 'Wire error 0x42')

    def test_all_hosted_ui_and_notification_messages_have_catalog_entries(self):
        base = catalog('en')
        for path in (ROOT/'qml').glob('*.qml'):
            text = path.read_text(encoding='utf8')
            self.assertNotRegex(text, '[\u4e00-\u9fff]')
            for key in re.findall(r'I18n\.tr\("([^"]+)"', text):
                self.assertIn(key, base, str(path))
        service = (ROOT/'quickshare/service.py').read_text(encoding='utf8')
        self.assertNotRegex(service, '[\u4e00-\u9fff]')
        for key in re.findall(r"_\('([^']+)'", service):
            self.assertIn(key, base)

if __name__ == '__main__':
    unittest.main()
