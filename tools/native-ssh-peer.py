"""Binary stdio adapter for the native probe on an explicitly selected test device."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import os
import shlex
import sys
import threading
import time
import paramiko


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--user', default='defaultuser')
    parser.add_argument('--binary', default='/usr/libexec/sfos-quickshare-native-probe')
    parser.add_argument('--interop', choices=('client', 'server'), required=True)
    args = parser.parse_args()
    if os.name == 'nt':
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    client = paramiko.SSHClient(); client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(args.host, username=args.user, password=os.environ['SFOS_TEST_PASSWORD'], timeout=10)
        channel = client.get_transport().open_session()
        channel.exec_command(shlex.quote(args.binary) + ' --interop ' + args.interop)
        def send():
            try:
                while True:
                    # Raw FD reads avoid a buffered-reader lock being held by
                    # the input thread if the peer finishes before stdin EOF.
                    data = os.read(sys.stdin.fileno(), 65536)
                    if not data: break
                    channel.sendall(data)
                channel.shutdown_write()
            except (OSError, EOFError):
                pass
        sender = threading.Thread(target=send, daemon=True)
        sender.start()
        deadline = time.monotonic() + 25
        while True:
            if channel.recv_ready():
                data = channel.recv(65536)
                sys.stdout.buffer.write(data); sys.stdout.buffer.flush()
            if channel.recv_stderr_ready():
                sys.stderr.buffer.write(channel.recv_stderr(65536)); sys.stderr.buffer.flush()
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                sender.join(timeout=.5)
                return channel.recv_exit_status()
            if time.monotonic() > deadline: raise TimeoutError('Native test peer timed out')
            time.sleep(.005)
    finally:
        client.close()


if __name__ == '__main__':
    raise SystemExit(main())
