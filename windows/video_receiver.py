"""
H.264 video receiver: TLS 1.3 client that reads VanCamera packets and decodes them.
"""
from __future__ import annotations

import socket
import ssl
import struct
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from certificate_handler import CertificateHandler

try:
    import av
    HAS_AV = True
    # PyAV 16+ exposes specific error types like InvalidDataError and FFmpegError,
    # but does NOT have av.AVError. Import the concrete error classes instead.
    try:
        from av import InvalidDataError, FFmpegError  # type: ignore
    except Exception:
        # Fallback: treat all exceptions as generic for decoding.
        InvalidDataError = FFmpegError = Exception  # type: ignore
except ImportError:
    HAS_AV = False
    print("Warning: PyAV is not installed. H.264 decoding will not work.")
    InvalidDataError = FFmpegError = Exception  # type: ignore


# Largest packet we accept. A 1080p keyframe is well under 1 MB; anything bigger means the
# stream is out of sync (or this is not a VanCamera server).
MAX_PACKET_SIZE = 8 * 1024 * 1024

FrameCallback = Callable[[np.ndarray, int, bool], None]


def parse_flags(flags_byte: int):
    """Returns (orientation_degrees, is_back_camera) from the packet flags byte."""
    orientation_degrees = (flags_byte & 0x03) * 90
    is_back_camera = (flags_byte & 0x80) != 0
    return orientation_degrees, is_back_camera


class StreamStalled(Exception):
    """No data received for too long (dead Wi-Fi link, phone asleep...)."""


@dataclass
class ReceiverStats:
    fps: float = 0.0
    kbps: float = 0.0
    width: int = 0
    height: int = 0
    frames_decoded: int = 0


class VideoReceiver:
    """Receives and decodes the H.264 stream from the phone."""

    CONNECT_TIMEOUT_S = 5.0
    # No data for this long = the link is dead. The phone sends ~30 packets/s while streaming,
    # so a few seconds of silence is never normal. Before, the receiver waited forever and the
    # picture just froze (issue #3).
    STALL_TIMEOUT_S = 5.0
    SOCKET_BUFFER_BYTES = 512 * 1024

    def __init__(self, host: str, port: int, cert_handler: CertificateHandler,
                 stall_timeout_s: Optional[float] = None):
        self.host = host
        self.port = port
        self.cert_handler = cert_handler
        self.stall_timeout_s = stall_timeout_s or self.STALL_TIMEOUT_S
        self.socket: Optional[socket.socket] = None
        self.ssl_socket: Optional[ssl.SSLSocket] = None
        self.is_running = False
        self.last_error: Optional[str] = None
        self.frame_callback: Optional[FrameCallback] = None
        self.disconnect_callback: Optional[Callable[[str], None]] = None
        self.receive_thread: Optional[threading.Thread] = None

        # Stats
        self._stats_lock = threading.Lock()
        self._bytes_received = 0
        self._frames_decoded = 0
        self._stats_snapshot = (time.monotonic(), 0, 0)
        self._last_size = (0, 0)
        self._last_data_time = time.monotonic()

        # H.264 decoder
        self.codec_context = None
        self.decode_error_count = 0
        self.frames_decoded = 0
        if HAS_AV:
            self._init_decoder()

    def _init_decoder(self):
        """Initializes the H.264 decoder with low-latency settings."""
        try:
            codec = av.CodecContext.create('h264', 'r')
            # Dimensions are auto-detected from SPS/PPS in the stream.
            # SLICE threading only: FRAME threading ('AUTO') buffers one frame per thread before
            # returning anything, which adds latency.
            codec.thread_type = 'SLICE'

            # === LOW LATENCY DECODER SETTINGS ===
            # Don't wait for B-frames or reordering.
            codec.options = {
                'flags': '+low_delay',
                'flags2': '+fast',
            }

            self.codec_context = codec
            self.decode_error_count = 0
            print("H.264 decoder initialized with low-latency settings")
        except Exception as e:
            print(f"Error initializing decoder: {e}")

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """
        Connects to the Android server.

        Returns:
            True if the connection was successful (``last_error`` explains failures)
        """
        self.last_error = None
        try:
            raw = socket.create_connection((self.host, self.port), timeout=self.CONNECT_TIMEOUT_S)

            # === LOW LATENCY NETWORK SETTINGS ===
            raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            raw.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            # A roomier buffer absorbs Wi-Fi bursts; we read continuously so it adds no latency.
            raw.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.SOCKET_BUFFER_BYTES)
            self.socket = raw

            ssl_context = self.cert_handler.create_ssl_context(
                verify_cert=self.cert_handler.cert_path is not None
            )
            self.ssl_socket = ssl_context.wrap_socket(
                raw,
                server_hostname=self.host if self.cert_handler.cert_path else None
            )
            # Short read timeout so the receive loop can notice stalls and stop requests.
            self.ssl_socket.settimeout(1.0)

            print(f"Connected to {self.host}:{self.port}")
            return True

        except socket.timeout:
            self.last_error = "Timed out. Is the phone streaming and on the same network?"
        except ConnectionRefusedError:
            self.last_error = "Connection refused. Tap Start streaming on the phone."
        except ssl.SSLError as e:
            self.last_error = f"TLS handshake failed: {e.reason or e}"
        except OSError as e:
            self.last_error = f"Network error: {e.strerror or e}"
        except Exception as e:
            self.last_error = str(e)
        print(f"Connection error: {self.last_error}")
        self._close_sockets()
        return False

    def _close_sockets(self):
        for sock in (self.ssl_socket, self.socket):
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
        self.ssl_socket = None
        self.socket = None

    def disconnect(self):
        """Disconnects from the server (no disconnect callback is fired)."""
        self.is_running = False
        self.disconnect_callback = None
        self._close_sockets()
        thread = self.receive_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2)

    def start_receiving(self):
        """Starts the receive thread."""
        if self.is_running:
            return

        if not self.ssl_socket:
            if not self.connect():
                return

        # Reinitialize decoder for fresh connection (ensures clean state)
        if HAS_AV:
            self._init_decoder()

        self._last_data_time = time.monotonic()
        self.is_running = True
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True, name="video-receive")
        self.receive_thread.start()

    # ------------------------------------------------------------------
    # Receive loop
    # ------------------------------------------------------------------

    def _receive_loop(self):
        """Main receive loop."""
        reason = "Connection closed by the phone"
        try:
            while self.is_running:
                size_data = self._receive_exact(4)
                if size_data is None:
                    break
                packet_size = struct.unpack('>I', size_data)[0]
                if packet_size < 2 or packet_size > MAX_PACKET_SIZE:
                    reason = f"Protocol error (packet size {packet_size})"
                    break

                # Packet = [1 byte flags][H.264 data]
                packet_data = self._receive_exact(packet_size)
                if packet_data is None:
                    break

                orientation_degrees, is_back_camera = parse_flags(packet_data[0])
                self._decode_frame(bytes(packet_data[1:]), orientation_degrees, is_back_camera)

        except StreamStalled:
            reason = f"No video for {self.stall_timeout_s:.0f} s (network stalled)"
        except Exception as e:
            reason = f"Receive error: {e}"

        was_running = self.is_running
        self.is_running = False
        self._close_sockets()
        print(f"Connection closed: {reason}")
        callback = self.disconnect_callback
        if was_running and callback:
            try:
                callback(reason)
            except Exception as e:
                print(f"Error in disconnect callback: {e}")

    def _receive_exact(self, size: int) -> Optional[bytearray]:
        """Receives exactly ``size`` bytes. Returns None when the connection closes."""
        buffer = bytearray(size)
        view = memoryview(buffer)
        received = 0
        while received < size:
            sock = self.ssl_socket
            if sock is None or not self.is_running:
                return None
            try:
                count = sock.recv_into(view[received:], size - received)
            except (socket.timeout, ssl.SSLWantReadError):
                if time.monotonic() - self._last_data_time > self.stall_timeout_s:
                    raise StreamStalled()
                continue
            except OSError:
                return None
            if count == 0:
                return None
            received += count
            self._last_data_time = time.monotonic()
            with self._stats_lock:
                self._bytes_received += count
        return buffer

    def _decode_frame(self, h264_data: bytes, orientation_degrees: int = 0, is_back_camera: bool = False):
        """Decodes one H.264 access unit using PyAV."""
        if not HAS_AV or not self.codec_context:
            return

        try:
            packet = av.Packet(h264_data)

            # Decode the packet - may produce 0, 1, or more frames.
            # Only use the LATEST frame to reduce latency.
            decoded_frames = self.codec_context.decode(packet)
            if not decoded_frames:
                return
            frame = decoded_frames[-1]
            self.decode_error_count = 0
            self.frames_decoded += len(decoded_frames)
            with self._stats_lock:
                self._frames_decoded += len(decoded_frames)
                self._last_size = (frame.width, frame.height)

            callback = self.frame_callback
            if callback:
                callback(frame.to_ndarray(format='rgb24'), orientation_degrees, is_back_camera)

        except (InvalidDataError, FFmpegError) as e:
            self.decode_error_count += 1
            # Only log first few errors and then periodically to avoid spam
            if self.decode_error_count <= 3 or self.decode_error_count % 100 == 0:
                print(f"Decode error ({self.decode_error_count}x): {e}")

            # If too many consecutive errors, try reinitializing the decoder
            if self.decode_error_count >= 50:
                print("Too many decode errors, reinitializing decoder...")
                self._init_decoder()
        except Exception as e:
            print(f"Unexpected decode error: {e}")

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def set_frame_callback(self, callback: FrameCallback):
        """
        Sets the callback for decoded frames. It runs on the receive thread and must be quick.

        Args:
            callback: function(frame_rgb: np.ndarray, orientation_degrees: int, is_back_camera: bool)
        """
        self.frame_callback = callback

    def set_disconnect_callback(self, callback: Callable[[str], None]):
        """Called once (from the receive thread) when an established stream ends unexpectedly."""
        self.disconnect_callback = callback

    def get_stats(self) -> ReceiverStats:
        """Rates since the previous call."""
        now = time.monotonic()
        with self._stats_lock:
            last_time, last_bytes, last_frames = self._stats_snapshot
            elapsed = max(now - last_time, 1e-3)
            stats = ReceiverStats(
                fps=(self._frames_decoded - last_frames) / elapsed,
                kbps=(self._bytes_received - last_bytes) * 8 / 1000 / elapsed,
                width=self._last_size[0],
                height=self._last_size[1],
                frames_decoded=self._frames_decoded,
            )
            self._stats_snapshot = (now, self._bytes_received, self._frames_decoded)
        return stats

    def is_connected(self) -> bool:
        """Checks whether the stream is active."""
        return self.is_running and self.ssl_socket is not None
