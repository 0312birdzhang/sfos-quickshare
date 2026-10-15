# SPDX-License-Identifier: GPL-3.0-or-later
import json
import unittest
from unittest.mock import Mock, patch
import test_peer_expiry as fixtures


class ReceivingCountdownTests(unittest.TestCase):
    setUp = fixtures.PeerExpiryTests.setUp
    def test_remaining_time_survives_repeated_status_requests(self):
        self.service.launch = Mock(return_value='receiver')
        with patch.object(self.module.time, 'monotonic', return_value=100):
            self.service.SetReceiving(True)
            self.assertEqual(json.loads(self.service.GetStatus())['receivingSeconds'], 600)
        with patch.object(self.module.time, 'monotonic', return_value=161):
            self.service.SetReceiving(True)  # Opening another page must not extend visibility.
            self.assertEqual(json.loads(self.service.GetStatus())['receivingSeconds'], 539)
        self.service.launch.assert_called_once_with('receive')

    def test_expiry_clears_receiving_and_countdown(self):
        self.service.receiver = 'receiver'
        self.service.receiver_deadline = 700
        self.service.Cancel = Mock()
        with patch.object(self.module.time, 'monotonic', return_value=700):
            status = json.loads(self.service.GetStatus())
        self.assertFalse(status['receiving'])
        self.assertEqual(status['receivingSeconds'], 0)
        self.service.Cancel.assert_called_once_with('receiver')

    def test_switch_off_resets_deadline(self):
        self.service.receiver = 'receiver'
        self.service.receiver_deadline = 700
        self.service.Cancel = Mock()
        self.service.SetReceiving(False)
        self.assertEqual(self.service.receiver_deadline, 0)
        self.assertEqual(self.service.receiving_seconds(), 0)
