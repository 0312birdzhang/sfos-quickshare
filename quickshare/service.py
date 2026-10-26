"""Session service. Network work runs in cancellable child processes."""
# SPDX-License-Identifier: GPL-3.0-or-later
import collections
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import uuid
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
from .i18n import tr as _, error_text, language

NAME = 'org.sailfishos.QuickShare'
PATH = '/org/sailfishos/QuickShare'
PEER_MAX_AGE = 15


class Service(dbus.service.Object):
    def __init__(self, bus):
        self.bus = bus
        self.name = dbus.service.BusName(NAME, bus=bus)
        super().__init__(bus, PATH)
        self.interface = os.environ.get('SFOS_QUICKSHARE_INTERFACE', 'auto')
        self.jobs = collections.OrderedDict()
        self.peers = {}
        self.peers_at = 0.0
        self.pending = {}
        self.receiver = None
        self.receiver_deadline = 0.0
        self.error = ''
        self.discovering = False
        self._replies = {}
        self.sent_history_deadlines = {}
        self.history_cleanup_scheduled = True
        self.bus.add_signal_receiver(self.transfer_status_changed, signal_name='statusChanged',
            dbus_interface='org.nemo.transferengine', bus_name='org.nemo.transferengine')
        GLib.timeout_add_seconds(5, self.clean_sent_history)

    def check(self):
        from .network import address
        from .worker import protocol_command
        try:
            address(self.interface)
            protocol_command()
        except Exception as error:
            raise dbus.exceptions.DBusException(error_text(error), name=NAME + '.LinkUnavailable')

    def launch(self, mode, *args):
        ident = uuid.uuid4().hex
        job = {'state': 'running', 'progress': 0.0, 'error': '', 'mode': mode}
        env = dict(os.environ)
        root = str(Path(__file__).resolve().parent.parent)
        env['PYTHONPATH'] = os.pathsep.join([root, str(Path(root) / 'vendor')])
        proc = subprocess.Popen([sys.executable, '-u', '-m', 'quickshare.worker', mode,
                                 self.interface, *args], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=env)
        self.jobs[ident] = (job, proc)
        def update(data):
            if job['state'] == 'canceled': return False
            if data.get('event') in ('ended', 'received', 'rejected'):
                for pending, request in list(self.pending.items()):
                    if request.get('wireId') == data.get('id'): self.Approve(pending, False)
            if 'peers' in data:
                self.peers = {p['id']: p for p in data.pop('peers')}
                self.peers_at = time.monotonic()
            if data.get('pin') and data['pin'] != job.get('pin'):
                self.notify(_('Quick Share sending PIN'), _('%1: ask the recipient to verify this PIN and accept.', data['pin']))
            job.update(data)
            if mode == 'receive' and data.get('incoming'): self.error = ''
            if data.get('error') and mode != 'send': self.error = data['error']
            return False
        def drain():
            errors = []
            def stderr():
                for line in proc.stderr:
                    errors.append(line.strip())
                    if len(errors) > 20: errors.pop(0)
            thread = threading.Thread(target=stderr, daemon=True)
            thread.start()
            for line in proc.stdout:
                try: GLib.idle_add(update, json.loads(line))
                except ValueError: pass
            code = proc.wait()
            thread.join()
            GLib.idle_add(finish, code, '\n'.join(errors))
        def finish(code, error):
            if job['state'] not in ('canceled', 'failed', 'finished'):
                job['state'] = 'finished' if code == 0 else 'failed'
                if code: job['error'] = error or 'Worker exited: ' + str(code)
            if mode == 'discover': self.discovering = False
            if mode == 'receive' and self.receiver == ident:
                for pending in list(self.pending): self.Approve(pending, False)
                self.receiver = None
                self.receiver_deadline = 0.0
                self.error = job.get('error', '')
            if mode == 'send':
                job['finishedAt'] = time.monotonic()
                GLib.timeout_add_seconds(60, self.expire_sent_jobs)
            # Keep bounded completed history without removing active jobs.
            for key in list(self.jobs):
                if len(self.jobs) <= 64: break
                if self.jobs[key][1].poll() is not None and key != ident:
                    self.jobs.pop(key)
            return False
        threading.Thread(target=drain, daemon=True).start()
        return ident

    def notify(self, title, body):
        try:
            iface = dbus.Interface(self.bus.get_object('org.freedesktop.Notifications', '/org/freedesktop/Notifications'), 'org.freedesktop.Notifications')
            iface.Notify('QuickShare', 0, '', title, body, dbus.Array([], signature='s'),
                         dbus.Dictionary({'x-nemo-preview-summary': title, 'x-nemo-preview-body': body}, signature='sv'), 10000)
        except dbus.DBusException:
            pass

    @dbus.service.method(NAME, in_signature='s', out_signature='')
    def SetLanguage(self, locale):
        os.environ['SFOS_QUICKSHARE_LANGUAGE'] = language(str(locale))

    @dbus.service.method(NAME, in_signature='', out_signature='s')
    def GetStatus(self):
        self.expire_sent_jobs()
        self.expire_peers()
        remaining = self.receiving_seconds()
        ready = True
        try: self.check()
        except dbus.DBusException: ready = False
        return json.dumps({'ready': ready, 'interface': self.interface,
                           'receiving': self.receiver is not None, 'discovering': self.discovering,
                           'receivingSeconds': remaining,
                           'peers': list(self.peers.values()), 'pending': list(self.pending.values()),
                           'jobs': [dict(value[0], id=key, error=error_text(value[0].get('error', ''))) for key, value in self.jobs.items()], 'error': error_text(self.error)})

    @dbus.service.method(NAME, in_signature='', out_signature='')
    def Discover(self):
        self.check()
        if not self.discovering:
            self.error = ''
            self.expire_peers()
            self.discovering = True
            try: self.launch('discover')
            except Exception:
                self.discovering = False
                raise

    @dbus.service.method(NAME, in_signature='ss', out_signature='s')
    def Send(self, source, peer):
        self.check()
        self.expire_peers()
        if peer not in self.peers:
            raise ValueError(_('Peer has expired; discover again'))
        if sum(proc.poll() is None for _, proc in self.jobs.values()) >= 5:
            raise ValueError(_('Too many active transfers'))
        if Path(source).is_symlink() or not Path(source).is_file(): raise ValueError(_('File does not exist'))
        return self.launch('send', json.dumps(self.peers[peer]), str(source))

    def expire_peers(self):
        # Discovery snapshots are leases, not a permanent device directory.
        if time.monotonic() - self.peers_at >= PEER_MAX_AGE:
            self.peers.clear()

    @dbus.service.method(NAME, in_signature='s', out_signature='s')
    def GetJob(self, ident):
        self.expire_sent_jobs()
        return json.dumps(dict(self.jobs[ident][0], error=error_text(self.jobs[ident][0].get('error', ''))))

    def expire_sent_jobs(self):
        now = time.monotonic()
        for ident, (job, proc) in list(self.jobs.items()):
            if (job['mode'] == 'send' and 'finishedAt' in job and
                    now - job['finishedAt'] >= 60 and proc.poll() is not None):
                self.jobs.pop(ident)
        return False

    def clean_sent_history(self):
        from .history import expire_sent
        try:
            api = dbus.Interface(self.bus.get_object('org.nemo.transferengine', '/org/nemo/transferengine'), 'org.nemo.transferengine')
            expire_sent(api, self.sent_history_deadlines, time.monotonic())
        except dbus.DBusException:
            self.history_cleanup_scheduled = False
            return False
        self.history_cleanup_scheduled = bool(self.sent_history_deadlines)
        return self.history_cleanup_scheduled

    def transfer_status_changed(self, ident, state):
        if int(state) in (3, 4, 5) and not self.history_cleanup_scheduled:
            self.history_cleanup_scheduled = True
            GLib.timeout_add_seconds(5, self.clean_sent_history)

    @dbus.service.method(NAME, in_signature='s', out_signature='')
    def Cancel(self, ident):
        job, proc = self.jobs[ident]
        if proc.poll() is None:
            job['state'] = 'canceled'
            proc.terminate()
            def kill():
                if proc.poll() is None: proc.kill()
                return False
            GLib.timeout_add_seconds(3, kill)

    @dbus.service.method(NAME, in_signature='b', out_signature='')
    def SetReceiving(self, enabled):
        if not enabled:
            if self.receiver: self.Cancel(self.receiver)
            self.receiver = None
            self.receiver_deadline = 0.0
            for ident in list(self.pending): self.Approve(ident, False)
            return
        self.check()
        if not self.receiver:
            self.error = ''
            self.receiver = self.launch('receive')
            self.receiver_deadline = time.monotonic() + 600
            # Everyone visibility expires, even when the settings page closes.
            receiver = self.receiver
            def expire():
                if self.receiver == receiver: self.SetReceiving(False)
                return False
            GLib.timeout_add_seconds(600, expire)

    def receiving_seconds(self):
        if not self.receiver:
            return 0
        remaining = max(0, math.ceil(self.receiver_deadline - time.monotonic()))
        if not remaining:
            self.SetReceiving(False)
        return remaining

    @dbus.service.method(NAME, in_signature='s', out_signature='b', async_callbacks=('reply', 'failure'))
    def Request(self, request, reply, failure):
        if not self.receiver:
            reply(False); return
        data = json.loads(request)
        if len(self.pending) >= 3:
            reply(False); return
        if not isinstance(data.get('pin'), str) or len(data['pin']) != 4 or not data['pin'].isascii() or not data['pin'].isdigit():
            reply(False); return
        ident = uuid.uuid4().hex
        self.pending[ident] = {'id': ident, 'wireId': data.get('id'), 'sender': data['sender'], 'files': data['files'], 'pin': str(data.get('pin', '')), 'total': data.get('total', 0)}
        self._replies[ident] = reply
        self.notify(_('Quick Share incoming request'), _('%1: verify PIN %2 in Settings → Quick Share.', data['sender'], data['pin']))
        def expire():
            if ident in self.pending: self.Approve(ident, False)
            return False
        GLib.timeout_add_seconds(45, expire)

    @dbus.service.method(NAME, in_signature='sb', out_signature='')
    def Approve(self, ident, accepted):
        reply = self._replies.pop(ident, None)
        self.pending.pop(ident, None)
        if reply: reply(bool(accepted))

    @dbus.service.method(NAME, in_signature='si', out_signature='')
    def Received(self, destination, count):
        from . import history
        files = history.received_files(destination, Path.home() / 'Downloads/QuickShare', count)
        self.notify(_('Quick Share receive complete'), files[0].name if len(files) == 1 else _('Saved files: %1. Folder: %2', count, destination))
        try:
            iface = dbus.Interface(self.bus.get_object('org.nemo.transferengine', '/org/nemo/transferengine'), 'org.nemo.transferengine')
            history.register(iface, destination, Path.home() / 'Downloads/QuickShare', 'Quick Share', count,
                             integer=dbus.Int64, callback=dbus.Array([], signature='s'))
        except dbus.DBusException as exc:
            self.error = 'Files saved; transfer history failed: ' + str(exc)

    def shutdown(self):
        for ident in list(self.jobs): self.Cancel(ident)


def main():
    import signal
    os.umask(0o077)
    DBusGMainLoop(set_as_default=True)
    service = Service(dbus.SessionBus())
    service._replies = {}
    loop = GLib.MainLoop()
    def stop(*args):
        service.shutdown()
        loop.quit()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    loop.run()


if __name__ == '__main__': main()
