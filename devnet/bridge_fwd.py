"""Temporary TCP forwarder, run on the Itential Gateway host over the same SSH session as the
reverse tunnel (see devnet/README.md).

The Gateway runner usually runs in a container on a Docker bridge network, so a reverse SSH
tunnel (which sshd binds to loopback) is invisible to it. This forwarder listens on the
bridge's gateway address and hands each connection to the tunnel. It exits when the SSH
session closes (stdin reaches EOF).

Environment:
  LISTEN_ADDR  bridge gateway address the runner can reach (default 172.18.0.1)
  PORT         port for both the listener and the tunnel end (default 2222)
"""

import os
import socket
import sys
import threading

LISTEN = (os.environ.get("LISTEN_ADDR", "172.18.0.1"), int(os.environ.get("PORT", "2222")))
TUNNEL = ("127.0.0.1", LISTEN[1])  # the ssh -R end of the tunnel to the switch


def pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while data := src.recv(65536):
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def serve() -> None:
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(LISTEN)
    srv.listen(8)
    print(f"bridge forwarder: {LISTEN[0]}:{LISTEN[1]} -> tunnel -> switch", flush=True)
    while True:
        client, peer = srv.accept()
        print(f"connection from {peer[0]}", flush=True)
        upstream = socket.create_connection(TUNNEL)
        threading.Thread(target=pipe, args=(client, upstream), daemon=True).start()
        threading.Thread(target=pipe, args=(upstream, client), daemon=True).start()


threading.Thread(target=serve, daemon=True).start()
sys.stdin.read()  # block until the SSH session closes, then exit
