# SPDX-License-Identifier: GPL-3.0-or-later
import collections
import json
import unittest
from unittest.mock import Mock, patch
import test_peer_expiry as fixtures
from quickshare.history import expire_sent


class SendExpiryTests(unittest.TestCase):
    setUp = fixtures.PeerExpiryTests.setUp

    def test_settings_history_expires_only_finished_sends(self):
        self.service.jobs = collections.OrderedDict()
        for ident, mode, state, ended, poll in [
                ('sent', 'send', 'finished', 100, 0),
                ('failed', 'send', 'failed', 100, 1),
                ('canceled', 'send', 'canceled', 100, -15),
                ('recent', 'send', 'finished', 101, 0),
                ('running', 'send', 'running', 0, None),
                ('received', 'receive', 'finished', 100, 0)]:
            job = dict(mode=mode, state=state, finishedAt=ended)
            self.service.jobs[ident] = (job, Mock(poll=Mock(return_value=poll)))
        with patch.object(self.module.time, 'monotonic', return_value=160):
            state = json.loads(self.service.GetStatus())
        self.assertEqual({job['id'] for job in state['jobs']}, {'recent', 'running', 'received'})

    def test_transfer_engine_cleanup_preserves_downloads_active_and_other_plugins(self):
        api = Mock()
        api.transfers.return_value = [[1, 1, 4, 1, 1., 'QuickShare'],
                                     [2, 1, 5, 1, 0., 'QuickShare'],
                                     [3, 1, 3, 1, 0., 'QuickShare'],
                                     [4, 1, 2, 1, 0., 'QuickShare'],
                                     [5, 2, 4, 1, 1., 'QuickShare'],
                                     [6, 1, 4, 1, 1., 'Bluetooth']]
        deadlines = {}
        expire_sent(api, deadlines, 100)
        expire_sent(api, deadlines, 159.9)
        api.clearTransfer.assert_not_called()
        expire_sent(api, deadlines, 160)
        self.assertEqual({call.args[0] for call in api.clearTransfer.call_args_list}, {1, 2, 3})
        self.assertEqual(deadlines, {})

    def test_restarted_or_removed_transfer_is_not_cleared(self):
        api = Mock()
        api.transfers.return_value = [[1, 1, 4, 1, 1., 'QuickShare']]
        deadlines = {}
        expire_sent(api, deadlines, 100)
        api.transfers.return_value = [[1, 1, 2, 1, 0., 'QuickShare']]
        expire_sent(api, deadlines, 200)
        api.clearTransfer.assert_not_called()
        self.assertEqual(deadlines, {})
