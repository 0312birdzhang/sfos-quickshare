"""Register actual received files, using Transfer Engine's local-path contract."""
# SPDX-License-Identifier: GPL-3.0-or-later
import mimetypes
from pathlib import Path
from urllib.parse import unquote


def received_files(destination, allowed_root, count):
    original = Path(destination)
    if original.is_symlink(): raise ValueError('Received batch cannot be a symlink')
    batch = original.resolve(strict=True)
    root = Path(allowed_root).resolve(strict=True)
    if batch.parent != root or not batch.is_dir():
        raise ValueError('Received batch is outside the inbox')
    files = []
    for path in batch.rglob('*'):
        if path.is_symlink(): raise ValueError('Symlink in received batch')
        if path.is_file():
            files.append(path)
            if len(files) > 10000: raise ValueError('Too many received files')
    if not 0 < count <= 10000 or len(files) != count:
        raise ValueError('Received file count does not match batch')
    return sorted(files)


def register(api, destination, allowed_root, label, count, integer=int, callback=()):
    files = received_files(destination, allowed_root, count)
    # A repeated completion/migration must not duplicate finished file entries.
    rows = api.transfers()
    ids = []
    for path in files:
        uri = unquote(path.as_uri())
        size = path.stat().st_size
        existing = next((int(row[0]) for row in rows if int(row[2]) == 4 and
                         unquote(str(row[6])) == uri and int(row[3]) == size), None)
        if existing is not None:
            ids.append(existing); continue
        kind = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        # createDownload calls QUrl::fromLocalFile itself: passing a URI produces
        # a second file: prefix and an unusable URL. Pass the real path instead.
        ident = api.createDownload(label, '', 'image://theme/icon-m-share',
                                   str(path), kind, integer(size), callback, '', '')
        if int(ident) <= 0: raise RuntimeError('Transfer Engine rejected received file')
        api.startTransfer(ident)
        api.finishTransfer(ident, 4, '')
        ids.append(int(ident))
    return ids
