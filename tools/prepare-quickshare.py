"""Prepare jars/runtime for RPM packaging after a successful Gradle build."""
# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

root = Path(__file__).resolve().parents[1] / 'quickshare'
lock = json.loads((root / 'runtime.lock.json').read_text())
archive = root / 'runtime' / lock['file']
assert hashlib.sha256(archive.read_bytes()).hexdigest() == lock['sha256'], 'Runtime checksum mismatch'
output = root / 'lib'; output.mkdir(exist_ok=True)
jars = list((root / 'jvm/bridge/build/install/bridge/lib').glob('*.jar'))
assert any(p.name == 'bridge.jar' for p in jars), 'Build :bridge:installDist first'
for source in jars: shutil.copyfile(source, output / source.name)
image = root / 'runtime-image'; image.mkdir(exist_ok=True)
with tarfile.open(archive) as tar:
    for member in tar.getmembers():
        if member.name.startswith('/') or '..' in Path(member.name).parts:
            raise ValueError('Unsafe runtime path')
        target = image / member.name
        if target.is_file() and (member.isfile() or member.issym() or member.islnk()):
            expected = tar.extractfile(member)
            with expected, target.open('rb') as existing:
                left, right = hashlib.sha256(), hashlib.sha256()
                for block in iter(lambda: expected.read(1024 * 1024), b''): left.update(block)
                for block in iter(lambda: existing.read(1024 * 1024), b''): right.update(block)
            if left.digest() != right.digest(): raise ValueError('Runtime image changed: ' + member.name)
        elif member.isdir() and target.is_dir():
            continue
        else:
            tar.extract(member, image, filter='data')
(root / 'artifacts.lock.json').write_text(json.dumps({
    'jars': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.glob('*.jar'))},
    'runtime_sha256': lock['sha256']}, indent=2), encoding='utf-8')
print('Prepared', len(jars), 'jars and verified runtime image')
