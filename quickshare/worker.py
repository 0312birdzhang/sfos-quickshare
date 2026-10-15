"""Isolated native discovery + Bada JVM protocol worker."""
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
from zeroconf import Zeroconf, IPVersion
from . import network
from .identity import device_name

ROOT = Path(__file__).resolve().parent


def emit(**fields):
    print(json.dumps(fields), flush=True)


def java_command():
    java = Path(os.environ.get('SFOS_QUICKSHARE_JAVA', '/usr/lib64/sfos-quickshare/runtime/bin/java'))
    library = Path(os.environ.get('SFOS_QUICKSHARE_LIB', str(ROOT / 'lib')))
    if not java.is_file() or not library.is_dir():
        raise RuntimeError('Quick Share protocol runtime is not installed')
    if not os.access(java, os.X_OK) or not (library / 'bridge.jar').is_file():
        raise RuntimeError('Quick Share protocol runtime is incomplete')
    if 'SFOS_QUICKSHARE_JAVA' not in os.environ:
        for name in ('lib/libjli.so', 'lib/server/libjvm.so', 'lib/libnet.so', 'lib/libnio.so'):
            if not (java.parent.parent / name).is_file():
                raise RuntimeError('Quick Share Java runtime is missing ' + name)
    return [str(java), '-Dfile.encoding=UTF-8', '-Xms16m', '-Xmx128m', '-XX:ActiveProcessorCount=2',
            '-cp', str(library / '*'), 'org.sailfishos.quickshare.MainKt']


def bridge(config, interface):
    env = dict(os.environ)
    # Sailfish images may advertise zh_CN.utf8 without installing that locale.
    # JDK 17 uses the native locale for filesystem paths independently of file.encoding.
    env['LC_ALL'] = 'en_US.utf8'
    process = subprocess.Popen(java_command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, encoding='utf-8', bufsize=1, env=env)
    output_lock = threading.Lock()
    def command(data):
        with output_lock:
            if process.poll() is None:
                try:
                    process.stdin.write(json.dumps(data) + '\n'); process.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
    command(config)
    def stop(*_):
        command({'command': 'stop' if config['command'] == 'receive' else 'cancel'})
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    errors = []
    def stderr():
        for line in process.stderr:
            errors.append(line.strip())
            if len(errors) > 15: errors.pop(0)
    thread = threading.Thread(target=stderr, daemon=True); thread.start()
    zc = info = None
    try:
        for line in process.stdout:
            data = json.loads(line)
            kind = data.get('event')
            if kind == 'listening':
                zc = Zeroconf(interfaces=[config['bind']], ip_version=IPVersion.V4Only)
                info = network.advertisement(config['bind'], data['port'], data['endpoint'], wifi_frequency=network.frequency(interface))
                zc.register_service(info)
                emit(listening=True, port=data['port'])
            elif kind == 'request':
                def consent(request):
                    try:
                        import dbus
                        api = dbus.Interface(dbus.SessionBus().get_object('org.sailfishos.QuickShare', '/org/sailfishos/QuickShare'), 'org.sailfishos.QuickShare')
                        accepted = bool(api.Request(json.dumps(request), timeout=55))
                    except Exception:
                        accepted = False
                    command({'command': 'approve', 'id': request['id'], 'accepted': accepted})
                threading.Thread(target=consent, args=(data,), daemon=True).start()
            elif kind == 'received':
                try:
                    import dbus
                    api = dbus.Interface(dbus.SessionBus().get_object('org.sailfishos.QuickShare', '/org/sailfishos/QuickShare'), 'org.sailfishos.QuickShare')
                    api.Received(data['destination'], data['count'])
                except Exception as error:
                    emit(error='Files saved; notification failed: ' + str(error))
                emit(incoming=data)
            else:
                emit(**data)
        code = process.wait()
        if code:
            raise RuntimeError('\n'.join(errors) or 'Protocol process failed')
    finally:
        if zc:
            if info: zc.unregister_service(info)
            zc.close()
        stop()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: process.kill(); process.wait()


def main():
    os.umask(0o077)
    mode, interface = sys.argv[1:3]
    if mode == 'discover':
        network.discover(interface, emit)
    elif mode == 'send':
        peer = json.loads(sys.argv[3])
        bridge({'command': 'send', 'host': peer['address'], 'port': peer['port'],
                'files': [sys.argv[4]], 'name': device_name()}, interface)
    elif mode == 'receive':
        bridge({'command': 'receive', 'bind': network.address(interface),
                'destination': str(Path.home() / 'Downloads/QuickShare'),
                'name': device_name()}, interface)
    else:
        raise ValueError('Unknown operation')


if __name__ == '__main__':
    try: main()
    except Exception as error:
        emit(state='failed', error=str(error))
        sys.exit(1)
