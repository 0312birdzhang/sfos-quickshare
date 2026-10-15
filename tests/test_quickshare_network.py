# SPDX-License-Identifier: GPL-3.0-or-later
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor'))
import unittest
from quickshare.network import advertisement, decode, encode, endpoint_name


class DiscoveryWireTests(unittest.TestCase):
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
