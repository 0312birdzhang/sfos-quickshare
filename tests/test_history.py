# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import tempfile
import unittest
from quickshare.history import register, received_files


class Engine:
    def __init__(self): self.calls, self.rows = [], []
    def transfers(self): return self.rows
    def createDownload(self, *args):
        self.calls.append(args)
        ident = len(self.calls)
        path = Path(args[3])
        self.rows.append([ident, 2, 4, args[5], 1.0, '', path.as_uri()])
        return ident
    def startTransfer(self, ident): pass
    def finishTransfer(self, ident, state, error): pass


class HistoryTests(unittest.TestCase):
    def test_image_and_unicode_name_register_real_paths_size_and_mime(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); batch = root / 'batch'; batch.mkdir()
            (batch / '3.jpg').write_bytes(b'jpeg')
            (batch / '照片.png').write_bytes(b'png')
            engine = Engine()
            register(engine, batch, root, 'Quick Share', 2)
            self.assertEqual({Path(call[3]).name for call in engine.calls}, {'3.jpg', '照片.png'})
            self.assertEqual({call[4] for call in engine.calls}, {'image/jpeg', 'image/png'})
            self.assertEqual({call[5] for call in engine.calls}, {3, 4})
            self.assertTrue(all(not call[3].startswith('file:') for call in engine.calls))
            register(engine, batch, root, 'Quick Share', 2)
            self.assertEqual(len(engine.calls), 2, 'Repeated completion duplicated history')

    def test_wrong_count_and_outside_inbox_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); batch = root / 'batch'; batch.mkdir(); (batch/'x').write_bytes(b'')
            with self.assertRaises(ValueError): received_files(batch, root, 2)
            other = root / 'other'; other.mkdir()
            with self.assertRaises(ValueError): received_files(batch, other, 1)


if __name__ == '__main__': unittest.main()
