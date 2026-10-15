"""Quick Share LAN discovery; no radio mode/configuration changes."""
# SPDX-License-Identifier: GPL-3.0-or-later
import base64
import ipaddress
import json
import os
import secrets
import socket
import subprocess
import threading
import time
from zeroconf import Zeroconf, ServiceInfo, ServiceBrowser, ServiceListener, IPVersion

TYPE = '_FC9F5ED42C8A._tcp.local.'


def encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=')


def decode(data):
    if not isinstance(data, bytes) or len(data) > 2048:
        raise ValueError('Invalid endpoint')
    return base64.b64decode(data + b'=' * (-len(data) % 4), altchars=b'-_', validate=True)


def endpoint_name(data):
    raw = decode(data)
    if len(raw) < 17:
        raise ValueError('Truncated endpoint')
    # Visibility/hidden is not a filter: stock peers enforce it during negotiation.
    if raw[0] & 16:
        return 'Quick Share device'
    if len(raw) < 18 or len(raw) < 18 + raw[17]:
        raise ValueError('Truncated device name')
    return raw[18:18 + raw[17]].decode('utf-8', 'replace') or 'Quick Share device'


def address(interface='auto'):
    if interface == 'auto':
        args = ['ip', '-j', 'route', 'show', 'default']
        routes = json.loads(subprocess.check_output(args, text=True))
        routes = sorted(routes, key=lambda row: row.get('metric', 0))
        interface = next((row['dev'] for row in routes if not row['dev'].startswith(('tun', 'wg', 'ppp'))), '')
    if not interface:
        raise RuntimeError('No local network connection')
    rows = json.loads(subprocess.check_output(['ip', '-j', 'address', 'show', 'dev', interface], text=True))
    for row in rows:
        for item in row.get('addr_info', []):
            if item.get('family') == 'inet' and item.get('scope') == 'global':
                return item['local']
    raise RuntimeError('Interface has no IPv4 address: ' + interface)


def frequency(interface):
    if interface == 'auto':
        interface = 'wlan0'
    try:
        result = subprocess.check_output(['iw', 'dev', interface, 'link'], text=True, stderr=subprocess.DEVNULL, timeout=2)
        for line in result.splitlines():
            if line.strip().startswith('freq:'):
                return str(int(float(line.split(':', 1)[1].strip())))
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


def advertisement(ip, port, endpoint, instance=None, wifi_frequency=None):
    ident = instance or ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789') for _ in range(4))
    if len(ident) != 4 or not ident.isascii() or not ident.isalnum():
        raise ValueError('Invalid endpoint ID')
    label = encode(b'\x23' + ident.encode('ascii') + b'\xfc\x9f\x5e\x00\x00').decode('ascii')
    props = {b'n': endpoint.encode('ascii'), b'ip': ip.encode('ascii')}
    if wifi_frequency:
        props[b'f'] = wifi_frequency.encode('ascii')
    return ServiceInfo(TYPE, label + '.' + TYPE, addresses=[socket.inet_aton(ip)],
                       port=port, properties=props, server='sfos-quickshare-' + ident + '.local.')


def discover(interface, emit, duration=8):
    ip = address(interface)
    local_ips = {ip}
    zc = Zeroconf(interfaces=[ip], ip_version=IPVersion.V4Only)
    found, lock = {}, threading.Lock()
    class Listener(ServiceListener):
        def add_service(self, z, kind, name):
            try:
                info = z.get_service_info(kind, name, timeout=1200)
                if not info or not info.addresses or not 0 < info.port <= 65535:
                    return
                raw = decode(name.split('.')[0].encode())
                if len(raw) != 10 or raw[0] != 0x23 or raw[5:8] != b'\xfc\x9f\x5e':
                    return
                # Resolve from DNS address records, not the unauthenticated TXT ip hint.
                remote = str(ipaddress.IPv4Address(info.addresses[0]))
                if remote in local_ips or ipaddress.ip_address(remote).is_multicast or ipaddress.ip_address(remote).is_unspecified:
                    return
                peer = {'id': name, 'name': endpoint_name(info.properties.get(b'n')), 'address': remote, 'port': info.port}
                with lock:
                    if len(found) < 128 or name in found:
                        found[name] = peer
            except (ValueError, TypeError, UnicodeError):
                return
        def update_service(self, z, kind, name):
            self.add_service(z, kind, name)
        def remove_service(self, z, kind, name):
            with lock:
                found.pop(name, None)
    browser = ServiceBrowser(zc, TYPE, Listener())
    try:
        end = time.monotonic() + duration
        while time.monotonic() < end:
            time.sleep(.5)
            with lock:
                emit(peers=list(found.values()))
    finally:
        browser.cancel()
        zc.close()
