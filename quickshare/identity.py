"""Use the system device identity without changing Bluetooth state."""
# SPDX-License-Identifier: GPL-3.0-or-later
import os
import socket


def clean_name(value):
    if not isinstance(value, str):
        return ''
    value = ''.join(c for c in value if c.isprintable()).strip()
    # Leave room for endpoint metadata and base64 inside the mDNS TXT record.
    return value.encode('utf-8')[:128].decode('utf-8', 'ignore').strip()


def bluetooth_name():
    try:
        import dbus
    except ImportError:
        return ''
    try:
        manager = dbus.Interface(dbus.SystemBus().get_object('org.bluez', '/',
            introspect=False), 'org.freedesktop.DBus.ObjectManager')
        objects = manager.GetManagedObjects(timeout=2)
        adapters = [interfaces['org.bluez.Adapter1'] for _, interfaces in sorted(objects.items())
                    if 'org.bluez.Adapter1' in interfaces]
        adapters.sort(key=lambda adapter: not bool(adapter.get('Powered', False)))
        for adapter in adapters:
            name = clean_name(adapter.get('Alias')) or clean_name(adapter.get('Name'))
            if name:
                return name
    except (dbus.DBusException, OSError):
        pass
    return ''


def device_name():
    explicit = clean_name(os.environ.get('SFOS_QUICKSHARE_NAME'))
    if explicit:
        return explicit
    name = bluetooth_name()
    if name:
        return name
    try:
        return clean_name(socket.gethostname()) or 'SailfishOS'
    except OSError:
        return 'SailfishOS'
