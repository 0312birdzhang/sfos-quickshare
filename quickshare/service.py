"""Session service. Network work runs in cancellable child processes."""
# SPDX-License-Identifier: GPL-3.0-or-later
import collections
import json
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

NAME = 'org.sailfishos.QuickShare'
PATH = '/org/sailfishos/QuickShare'


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
        self.error = ''
        self.discovering = False
        self._replies = {}

    def check(self):
        from .network import address
        from .worker import java_command
        try:
            address(self.interface)
            java_command()
        except Exception as error:
            raise dbus.exceptions.DBusException(str(error), name=NAME + '.LinkUnavailable')

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
                self.notify('Quick Share 发送 PIN', data['pin'] + '：请接收方核对后确认')
            job.update(data)
            if data.get('error'): self.error = data['error']
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
                self.error = job.get('error', '')
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

    @dbus.service.method(NAME, in_signature='', out_signature='s')
    def GetStatus(self):
        ready = True
        try: self.check()
        except dbus.DBusException: ready = False
        return json.dumps({'ready': ready, 'interface': self.interface,
                           'receiving': self.receiver is not None, 'discovering': self.discovering,
                           'peers': list(self.peers.values()), 'pending': list(self.pending.values()),
                           'jobs': [dict(value[0], id=key) for key, value in self.jobs.items()], 'error': self.error})

    @dbus.service.method(NAME, in_signature='', out_signature='')
    def Discover(self):
        self.check()
        if not self.discovering:
            self.error = ''
            self.peers = {}
            self.discovering = True
            try: self.launch('discover')
            except Exception:
                self.discovering = False
                raise

    @dbus.service.method(NAME, in_signature='ss', out_signature='s')
    def Send(self, source, peer):
        self.check()
        if peer not in self.peers or time.monotonic() - self.peers_at > 120:
            raise ValueError('Peer has expired; discover again')
        if sum(proc.poll() is None for _, proc in self.jobs.values()) >= 5:
            raise ValueError('Too many active transfers')
        if Path(source).is_symlink() or not Path(source).is_file(): raise ValueError('File does not exist')
        return self.launch('send', json.dumps(self.peers[peer]), str(source))

    @dbus.service.method(NAME, in_signature='s', out_signature='s')
    def GetJob(self, ident):
        return json.dumps(self.jobs[ident][0])

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
            for ident in list(self.pending): self.Approve(ident, False)
            return
        self.check()
        if not self.receiver:
            self.error = ''
            self.receiver = self.launch('receive')
            # Everyone visibility expires, even when the settings page closes.
            receiver = self.receiver
            def expire():
                if self.receiver == receiver: self.SetReceiving(False)
                return False
            GLib.timeout_add_seconds(600, expire)

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
        self.notify('Quick Share 接收请求', data['sender'] + '：确认 PIN ' + data['pin'] + '，打开设置 → Quick Share')
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
        self.notify('Quick Share 接收完成', files[0].name if len(files) == 1 else str(count) + ' 个文件已保存到 ' + destination)
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
