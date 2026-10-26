# SPDX-License-Identifier: GPL-3.0-or-later
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'posix', 'Shell scriptlet simulations run on Linux/WSL')
class PackageLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / 'state'
        self.state.write_text('static')
        self.log = self.root / 'log'
        self.marker = self.root / 'transaction'
        helper = self.root / 'systemctl-user'
        helper.write_text('''#!/bin/sh
echo "$*" >> "$CALL_LOG"
case "$1" in
    is-enabled) cat "$STATE_FILE" ;;
    mask) echo masked-runtime > "$STATE_FILE" ;;
    unmask) echo static > "$STATE_FILE" ;;
esac
''')
        helper.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.root) + ':' + os.environ['PATH'],
                        CALL_LOG=str(self.log), STATE_FILE=str(self.state))
        self.spec = (ROOT / 'rpm/sfos-quickshare.spec').read_text()

    def script(self, name, count):
        match = re.search(r'^%' + name + r'\n(.*?)(?=^%[a-z]|\Z)', self.spec, re.M | re.S)
        self.assertIsNotNone(match, name)
        code = match[1].replace('/run/sfos-quickshare-rpm', str(self.marker))
        subprocess.run(['/bin/sh', '-eu', '-c', code, name, str(count)],
                       env=self.env, check=True, capture_output=True, text=True)

    def test_upgrade_from_old_package_blocks_activation_then_restores_on_demand(self):
        self.script('pre', 2)
        self.assertEqual(self.state.read_text().strip(), 'masked-runtime')
        self.assertTrue((self.marker / 'unmask').exists())
        self.script('posttrans', 2)
        self.assertEqual(self.state.read_text().strip(), 'static')
        self.assertFalse((self.marker / 'unmask').exists())
        self.assertNotIn('start ', self.log.read_text())

    def test_final_uninstall_stops_service_and_removes_only_transaction_mask(self):
        self.script('preun', 0)
        self.assertEqual(self.state.read_text().strip(), 'masked-runtime')
        self.script('postun', 0)
        self.assertEqual(self.state.read_text().strip(), 'static')
        self.assertIn('mask --runtime sfos-quickshare.service', self.log.read_text())

    def test_old_package_upgrade_cleanup_does_not_stop_new_service(self):
        self.script('preun', 1)
        self.script('postun', 1)
        self.assertFalse(self.log.exists())

    def test_user_mask_is_preserved(self):
        self.state.write_text('masked')
        self.script('pre', 2)
        self.script('posttrans', 2)
        self.assertEqual(self.state.read_text().strip(), 'masked')
        self.assertNotIn('unmask', self.log.read_text())
