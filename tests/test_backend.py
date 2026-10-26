# SPDX-License-Identifier: GPL-3.0-or-later
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor'))
from quickshare import worker


class BackendTests(unittest.TestCase):
    def test_native_binary_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            binary=Path(folder)/'native';binary.write_bytes(b'test');binary.chmod(0o755)
            with patch.dict(os.environ,{'SFOS_QUICKSHARE_NATIVE':str(binary)},clear=True):
                self.assertEqual(worker.protocol_command(),[str(binary)])

    def test_missing_native_binary_is_an_error(self):
        with patch.dict(os.environ,{'SFOS_QUICKSHARE_NATIVE':'/nonexistent/native-worker'},clear=True):
            with self.assertRaises(RuntimeError):worker.protocol_command()

    def test_removed_and_unknown_backends_are_rejected(self):
        for name in ('jvm','invalid'):
            with self.subTest(backend=name), patch.dict(os.environ,{'SFOS_QUICKSHARE_BACKEND':name},clear=True):
                with self.assertRaises(RuntimeError):worker.protocol_command()
