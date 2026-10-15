# SPDX-License-Identifier: GPL-3.0-or-later
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor'))
import unittest
from unittest.mock import patch
from quickshare import network
from quickshare.network import advertisement, decode, encode, endpoint_name


class DiscoveryWireTests(unittest.TestCase):
    def test_goodbye_removes_peer_from_live_snapshots(self):
        info = advertisement('192.0.2.20', 34567,
            encode(bytes([0x24]) + bytes(16) + bytes([4]) + b'Peer').decode(), 'Ab12')
        now = [0.0]
        listener = []
        snapshots = []
        class Server:
            def get_service_info(self, *args, **kwargs): return info
            def close(self): pass
        class Browser:
            def __init__(self, server, kind, callback):
                listener.append(callback)
                callback.add_service(server, kind, info.name)
            def cancel(self): pass
        def sleep(seconds):
            now[0] += seconds
            if now[0] >= 1:
                listener[0].remove_service(None, network.TYPE, info.name)
        with patch.object(network, 'address', return_value='192.0.2.10'), \
             patch.object(network, 'Zeroconf', return_value=Server()), \
             patch.object(network, 'ServiceBrowser', Browser), \
             patch.object(network.time, 'monotonic', side_effect=lambda: now[0]), \
             patch.object(network.time, 'sleep', side_effect=sleep):
            network.discover('auto', lambda **data: snapshots.append(data['peers']), duration=2)
        self.assertEqual(snapshots[0][0]['id'], info.name)
        self.assertEqual(snapshots[-1], [])

    def test_instance_and_stock_txt_shape(self):
        raw = bytes([0x24]) + bytes(16) + bytes([6]) + b'SailOS'
        info = advertisement('192.0.2.10', 34567, encode(raw).decode(), 'Ab12', '2437')
        self.assertEqual(decode(info.name.split('.')[0].encode()), b'\x23Ab12\xfc\x9f\x5e\x00\x00')
        self.assertEqual(info.properties[b'ip'], b'192.0.2.10')
        self.assertEqual(info.properties[b'f'], b'2437')
        self.assertEqual(endpoint_name(info.properties[b'n']), 'SailOS')

    def test_hidden_device_remains_discoverable(self):
        self.assertEqual(endpoint_name(encode(bytes([0x34]) + bytes(16))), 'Quick Share device')

    def test_truncated_or_invalid_endpoint_is_rejected(self):
        for data in [None, b'!!!!', encode(b'\x24'), encode(bytes([0x24])+bytes(16)+bytes([10])+b'a')]:
            with self.assertRaises(ValueError): endpoint_name(data)


if __name__ == '__main__': unittest.main()
