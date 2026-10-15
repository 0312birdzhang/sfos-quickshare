"""Exercise the real service methods without requiring a session bus."""
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


def load_service():
    dbus = types.ModuleType('dbus')
    api = types.ModuleType('dbus.service')
    api.Object = object
    api.method = lambda *args, **kwargs: lambda fn: fn
    dbus.service = api
    dbus.DBusException = RuntimeError
    modules = {'dbus': dbus, 'dbus.service': api,
               'dbus.mainloop': types.ModuleType('dbus.mainloop'),
               'dbus.mainloop.glib': types.SimpleNamespace(DBusGMainLoop=Mock()),
               'gi': types.ModuleType('gi'),
               'gi.repository': types.SimpleNamespace(GLib=Mock())}
    spec = importlib.util.spec_from_file_location('quickshare._service_test',
        Path(__file__).resolve().parents[1] / 'quickshare/service.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class PeerExpiryTests(unittest.TestCase):
    def setUp(self):
        self.module = load_service()
        self.service = self.module.Service.__new__(self.module.Service)
        self.service.peers = {'peer': {'id': 'peer'}}
        self.service.peers_at = 100
        self.service.check = Mock()
        self.service.interface = 'auto'
        self.service.receiver = None
        self.service.receiver_deadline = 0.0
        self.service.discovering = False
        self.service.pending = {}
        self.service.jobs = {}
        self.service.error = ''

    def test_status_removes_stale_devices_at_lease_boundary(self):
        with patch.object(self.module.time, 'monotonic', return_value=115):
            self.assertEqual(json.loads(self.service.GetStatus())['peers'], [])
            self.assertEqual(self.service.peers, {})

    def test_fresh_snapshot_remains_visible(self):
        with patch.object(self.module.time, 'monotonic', return_value=114.9):
            self.assertEqual(len(json.loads(self.service.GetStatus())['peers']), 1)

    def test_send_cannot_use_expired_device_without_status_poll(self):
        with patch.object(self.module.time, 'monotonic', return_value=700):
            with self.assertRaises(ValueError):
                self.service.Send('unused', 'peer')
        self.assertEqual(self.service.peers, {})
