"""Fetch pinned Python modules for discovery; honor standard proxy env vars."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def fetch(url, digest):
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('Checksum mismatch: ' + url)
    return data

def write(base, name, data):
    relative = Path(name)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Unsafe dependency path')
    target = base / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)

def main():
    vendor = ROOT / 'vendor'
    for item in json.loads((ROOT / 'dependencies.lock.json').read_text()):
        data = fetch(item['url'], item['sha256'])
        if item['name'] == 'zeroconf':
            with tarfile.open(fileobj=io.BytesIO(data)) as archive:
                for member in archive.getmembers():
                    if not member.isfile():
                        continue
                    if '/src/zeroconf/' in member.name:
                        name = 'zeroconf/' + member.name.split('/src/zeroconf/', 1)[1]
                    elif Path(member.name).name.startswith('LICENSE'):
                        name = 'zeroconf/' + Path(member.name).name
                    else:
                        continue
                    write(vendor, name, archive.extractfile(member).read())
        else:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for member in archive.infolist():
                    if not member.is_dir():
                        write(vendor, member.filename, archive.read(member))
        print('Verified', item['name'], item['version'])

if __name__ == '__main__':
    main()
