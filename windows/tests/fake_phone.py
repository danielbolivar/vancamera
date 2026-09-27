"""
A fake VanCamera phone for tests: a TLS 1.3 server that streams real H.264 (libx264) using the
same packet format as the Android app.
"""
from __future__ import annotations

import datetime
from fractions import Fraction
import socket
import ssl
import struct
import threading
import time
from pathlib import Path
from typing import List, Optional

import av
import numpy as np
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def make_certificate(directory: Path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "VanCamera")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    cert_path = directory / "cert.pem"
    key_path = directory / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))
    return cert_path, key_path


def encode_h264(frame_count: int = 60, width: int = 320, height: int = 240) -> List[bytes]:
    """Baseline-style H.264 access units in Annex B with SPS/PPS on every keyframe."""
    codec = av.CodecContext.create("libx264", "w")
    codec.width = width
    codec.height = height
    codec.pix_fmt = "yuv420p"
    codec.framerate = 30
    codec.time_base = Fraction(1, 30)
    codec.options = {"preset": "ultrafast", "tune": "zerolatency",
                     "x264-params": "keyint=15:repeat-headers=1:bframes=0"}
    packets: List[bytes] = []
    for i in range(frame_count):
        img = np.zeros((height, width, 3), dtype=np.uint8)
        img[:, : (i * 5) % width] = (200, 50, 50)
        frame = av.VideoFrame.from_ndarray(img, format="rgb24").reformat(format="yuv420p")
        frame.pts = i
        packets.extend(bytes(p) for p in codec.encode(frame))
    packets.extend(bytes(p) for p in codec.encode(None))
    return packets


def packet(payload: bytes, flags: int) -> bytes:
    return struct.pack(">I", 1 + len(payload)) + bytes([flags]) + payload


class FakePhone:
    def __init__(self, tmp_path: Path, port: int = 0, flags: int = 0x81, fps: int = 30):
        self.cert_path, self.key_path = make_certificate(tmp_path)
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.minimum_version = ssl.TLSVersion.TLSv1_3
        self.context.load_cert_chain(str(self.cert_path), str(self.key_path))
        self.flags = flags
        self.interval = 1.0 / fps
        self.packets = encode_h264()
        self.requested_port = port
        self.port: Optional[int] = None
        self.server: Optional[socket.socket] = None
        self.clients: List[ssl.SSLSocket] = []
        self.connections = 0
        self.paused = threading.Event()        # stop sending but keep the socket open
        self.max_packets: Optional[int] = None  # close the client after this many packets
        self.bad_size = False
        self._running = False

    def start(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", self.requested_port))
        self.server.listen(5)
        self.port = self.server.getsockname()[1]
        self._running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()
        return self

    def _accept_loop(self):
        while self._running:
            try:
                raw, _ = self.server.accept()
            except OSError:
                return
            try:
                client = self.context.wrap_socket(raw, server_side=True)
            except (ssl.SSLError, OSError):
                raw.close()
                continue
            self.connections += 1
            self.clients.append(client)
            threading.Thread(target=self._stream, args=(client,), daemon=True).start()

    def _stream(self, client: ssl.SSLSocket):
        sent = 0
        try:
            if self.bad_size:
                client.sendall(struct.pack(">I", 0x7FFFFFFF))
                time.sleep(2)
                return
            while self._running:
                for payload in self.packets:
                    while self.paused.is_set() and self._running:
                        time.sleep(0.05)
                    if not self._running:
                        return
                    client.sendall(packet(payload, self.flags))
                    sent += 1
                    if self.max_packets is not None and sent >= self.max_packets:
                        return
                    time.sleep(self.interval)
        except OSError:
            pass
        finally:
            try:
                client.close()
            except OSError:
                pass

    def stop(self):
        self._running = False
        if self.server:
            self.server.close()
        for c in self.clients:
            try:
                c.close()
            except OSError:
                pass
