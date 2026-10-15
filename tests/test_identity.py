# SPDX-License-Identifier: GPL-3.0-or-later
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor'))
from quickshare import identity
from quickshare import worker
from quickshare.network import advertisement, encode, endpoint_name


class IdentityTests(unittest.TestCase):
    def test_sender_and_receiver_use_the_same_system_name(self):
        for mode, args in [('send', ['{"address":"192.0.2.20","port":1234}', '/test.jpg']),
                           ('receive', [])]:
            with patch.object(worker, 'device_name', return_value='My tablet'), \
                 patch.object(worker.network, 'address', return_value='192.0.2.10'), \
                 patch.object(worker, 'bridge') as bridge, \
                 patch.object(worker.os, 'umask'), \
                 patch.object(sys, 'argv', ['worker', mode, 'auto'] + args):
                worker.main()
                self.assertEqual(bridge.call_args[0][0]['name'], 'My tablet')

    def test_bluetooth_alias_is_used_even_when_powered_off(self):
        manager = Mock()
        manager.GetManagedObjects.return_value = {'/org/bluez/hci0': {
            'org.bluez.Adapter1': {'Alias': 'Xiaomi Pad 5', 'Name': 'Other', 'Powered': False}}}
        dbus = types.SimpleNamespace(Interface=Mock(return_value=manager),
                                    SystemBus=Mock(), DBusException=RuntimeError)
        with patch.dict(sys.modules, {'dbus': dbus}), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(identity.device_name(), 'Xiaomi Pad 5')
        manager.GetManagedObjects.assert_called_once_with(timeout=2)

    def test_dbus_failure_falls_back_to_hostname(self):
        dbus = types.SimpleNamespace(Interface=Mock(), SystemBus=Mock(side_effect=RuntimeError), DBusException=RuntimeError)
        with patch.dict(sys.modules, {'dbus': dbus}), patch.dict(os.environ, {}, clear=True), \
             patch.object(identity.socket, 'gethostname', return_value='XiaomiPad5'):
            self.assertEqual(identity.device_name(), 'XiaomiPad5')

    def test_override_and_empty_fallback(self):
        with patch.object(identity, 'bluetooth_name', return_value='Bluetooth'), \
             patch.dict(os.environ, {'SFOS_QUICKSHARE_NAME': ' My tablet '}):
            self.assertEqual(identity.device_name(), 'My tablet')
        with patch.object(identity, 'bluetooth_name', return_value=''), \
             patch.dict(os.environ, {'SFOS_QUICKSHARE_NAME': '\n'}), \
             patch.object(identity.socket, 'gethostname', return_value=''):
            self.assertEqual(identity.device_name(), 'SailfishOS')

    def test_unicode_name_fits_real_mdns_record(self):
        name = identity.clean_name('平板😀' * 100 + '\x00\n')
        self.assertLessEqual(len(name.encode('utf8')), 128)
        raw = bytes([0x24]) + bytes(16) + bytes([len(name.encode('utf8'))]) + name.encode('utf8')
        info = advertisement('192.0.2.10', 1234, encode(raw).decode(), 'Ab12')
        self.assertEqual(endpoint_name(info.properties[b'n']), name)
