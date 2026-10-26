"""Real TCP native-worker tests; isolated files and explicit synthetic consent."""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import queue
import socket
import stat
import subprocess
import tempfile
import threading
import time


class Peer:
    def __init__(self, binary, config):
        self.process = subprocess.Popen([binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf8')
        self.events = queue.Queue()
        self.history = []
        def collect():
            for line in self.process.stdout:
                self.events.put(json.loads(line))
        self.reader = threading.Thread(target=collect, daemon=True); self.reader.start()
        self.command(config)

    def command(self, command):
        self.process.stdin.write(json.dumps(command) + '\n'); self.process.stdin.flush()

    def until(self, predicate, timeout=15):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try: event = self.events.get(timeout=.2)
            except queue.Empty: continue
            self.history.append(event)
            if predicate(event): return event
        raise AssertionError(self.history)

    def stop(self):
        if self.process.poll() is None:
            try: self.command({'command': 'stop'})
            except (BrokenPipeError, OSError): pass
            try: self.process.wait(timeout=5)
            except subprocess.TimeoutExpired: self.process.kill(); self.process.wait(); raise
        self.reader.join(timeout=2)
        error = self.process.stderr.read()
        if 'AddressSanitizer' in error or 'runtime error:' in error: raise AssertionError(error)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr): stream.close()


def start(binary, folder):
    peer = Peer(binary, {'command':'receive','bind':'127.0.0.1','destination':str(folder),'name':'Native receiver'})
    return peer, peer.until(lambda e:e.get('event')=='listening')['port']


def sender(binary, port, paths):
    return Peer(binary, {'command':'send','host':'127.0.0.1','port':port,'files':[str(p) for p in paths],'name':'Native sender'})


def approve(receiver, sender_peer):
    request = receiver.until(lambda e:e.get('event')=='request')
    waiting = sender_peer.until(lambda e:e.get('state')=='waiting')
    assert request['pin'] == waiting['pin'] and len(request['pin'])==4
    receiver.command({'command':'approve','id':request['id'],'accepted':True})
    return request


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def run(binary):
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        first = root/'first'; second = root/'second'; first.mkdir(); second.mkdir()
        files = [first/'测试-😀.pdf', first/'empty.txt', first/'same.jpg', second/'same.jpg']
        for path, content in zip(files, [os.urandom(1024*1024+7), b'', b'first jpeg', b'second jpeg']): path.write_bytes(content)
        receiver, port = start(binary, root/'received'); sending = sender(binary, port, files)
        try:
            request = approve(receiver, sending)
            assert len(request['files'])==4
            sending.until(lambda e:e.get('state')=='finished')
            arrived = receiver.until(lambda e:e.get('event')=='received')
            saved = list(Path(arrived['destination']).iterdir())
            assert collections.Counter(map(digest,saved)) == collections.Counter(map(digest,files))
            assert all(stat.S_IMODE(p.stat().st_mode)==0o600 for p in saved)
            assert stat.S_IMODE(Path(arrived['destination']).stat().st_mode)==0o700
            assert not list((root/'received').glob('.pending-*'))
            # A discovery/probe TCP connection after a successful transfer must
            # not replace that success with a receive error. The real interrupted
            # transfer below must still report failure and clean staging.
            with socket.create_connection(('127.0.0.1', port)) as probe:
                probe.sendall(b'\x00\x00')
            time.sleep(.4)
            while True:
                try: extra = receiver.events.get_nowait()
                except queue.Empty: break
                assert not extra.get('error'), extra
            print('Native TCP: matching PIN, multichunk, Unicode, empty and duplicate filenames, hashes and private permissions PASS', flush=True)
        finally: sending.stop(); receiver.stop()

        # Cut the upstream TCP stream in the middle of an encrypted file frame.
        # The public batch must never appear, and the partial private batch must
        # be removed before the receiver reports failure.
        large=root/'interrupted.bin';large.write_bytes(os.urandom(10*1024*1024))
        receiver, target_port = start(binary, root/'interrupted')
        proxy=socket.socket();proxy.bind(('127.0.0.1',0));proxy.listen(1)
        def relay_back(remote,client):
            try:
                while True:
                    value=remote.recv(65536)
                    if not value:break
                    client.sendall(value)
            except OSError:pass
            finally:
                try:client.shutdown(socket.SHUT_WR)
                except OSError:pass
        def break_stream():
            client,_=proxy.accept();remote=socket.create_connection(('127.0.0.1',target_port))
            back=threading.Thread(target=relay_back,args=(remote,client),daemon=True);back.start()
            count=0
            try:
                while count<800000:
                    value=client.recv(min(65536,800000-count))
                    if not value:break
                    remote.sendall(value);count+=len(value)
            except OSError:pass
            finally:
                remote.shutdown(socket.SHUT_RDWR);client.shutdown(socket.SHUT_RDWR)
                remote.close();client.close();back.join(timeout=2)
        transfer=threading.Thread(target=break_stream,daemon=True);transfer.start()
        sending=sender(binary,proxy.getsockname()[1],[large])
        try:
            approve(receiver,sending)
            receiver.until(lambda e:e.get('event')=='ended')
            sending.until(lambda e:e.get('state') in ('failed','canceled'))
            assert not list((root/'interrupted').iterdir())
            print('Native TCP: interrupted encrypted stream publishes nothing and removes private partial data PASS',flush=True)
        finally:sending.stop();receiver.stop();proxy.close();transfer.join(timeout=2)

        receiver, port = start(binary, root/'declined'); sending = sender(binary, port, files[:1])
        try:
            request = receiver.until(lambda e:e.get('event')=='request')
            receiver.command({'command':'approve','id':request['id'],'accepted':False})
            receiver.until(lambda e:e.get('event')=='rejected')
            sending.until(lambda e:e.get('state')=='failed')
            assert not (root/'declined').exists()
            print('Native TCP: refusal creates no files or staging directory PASS', flush=True)
        finally: sending.stop(); receiver.stop()

        receiver, port = start(binary, root/'canceled'); sending = sender(binary, port, files[:1])
        try:
            receiver.until(lambda e:e.get('event')=='request')
            sending.command({'command':'cancel'})
            sending.until(lambda e:e.get('state')=='canceled')
            receiver.until(lambda e:e.get('event')=='ended')
            assert not (root/'canceled').exists()
            print('Native TCP: cancel during approval cleans pending request without saving data PASS', flush=True)
        finally: sending.stop(); receiver.stop()

        outside = root/'outside'; outside.mkdir(); linked=root/'linked'; linked.symlink_to(outside, target_is_directory=True)
        receiver, port = start(binary, linked); sending = sender(binary, port, files[:1])
        try:
            approve(receiver,sending)
            receiver.until(lambda e:e.get('event')=='ended')
            sending.until(lambda e:e.get('state') in ('failed','canceled'))
            assert not list(outside.iterdir())
            print('Native TCP: symlink destination rejected without writing through it PASS', flush=True)
        finally: sending.stop(); receiver.stop()


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--binary',required=True);args=parser.parse_args()
    run(args.binary)
