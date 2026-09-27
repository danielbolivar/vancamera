"""
Streaming session management, independent of the UI toolkit.

Threads:
- worker thread: connects, waits while streaming, reconnects with backoff after a drop;
- receive thread (inside VideoReceiver): reads packets and decodes every frame (H.264 needs
  every frame), then hands the newest decoded frame over and returns immediately;
- processing thread: orients the newest frame, feeds the virtual camera and prepares the preview.
  If it falls behind, intermediate frames are skipped instead of queueing up (no growing lag).

The UI only calls start()/stop() and polls get_preview_frame()/stats, so a slow UI can never
block the network (the old code did all of this on the receive thread, and called Tk from it).
"""

from __future__ import annotations

import enum
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import numpy as np

import frame_transform
from adb_forward import ensure_port_forward
from certificate_handler import CertificateHandler
from device_discovery import DiscoveredDevice
from video_receiver import ReceiverStats, VideoReceiver
from virtual_cam_bridge import VirtualCamBridge


class StreamState(enum.Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    STREAMING = "streaming"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class StreamStatus:
    state: StreamState
    message: str = ""
    device: Optional[DiscoveredDevice] = None


class StreamController:
    RECONNECT_DELAYS_S = (1.0, 2.0, 3.0, 5.0)

    def __init__(
        self,
        cert_handler: CertificateHandler,
        vcam_size: Tuple[int, int] = (1280, 720),
        vcam_fps: int = 30,
        receiver_factory: Callable[..., VideoReceiver] = VideoReceiver,
        vcam_factory: Callable[..., VirtualCamBridge] = VirtualCamBridge,
        port_forwarder: Callable[..., bool] = ensure_port_forward,
    ):
        self.cert_handler = cert_handler
        self.vcam_size = vcam_size
        self.vcam_fps = vcam_fps
        self._receiver_factory = receiver_factory
        self._vcam_factory = vcam_factory
        self._port_forwarder = port_forwarder

        self._listeners: list = []
        self._status = StreamStatus(StreamState.IDLE)
        self._lock = threading.Lock()

        self._worker: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._receiver: Optional[VideoReceiver] = None
        self._disconnected = threading.Event()
        self._disconnect_reason = ""
        self._vcam: Optional[VirtualCamBridge] = None
        self.vcam_error: Optional[str] = None
        self.vcam_device: Optional[str] = None

        # Latest decoded frame handed over by the receive thread.
        self._frame_lock = threading.Lock()
        self._frame_ready = threading.Event()
        self._pending_frame: Optional[Tuple[np.ndarray, int, bool]] = None
        self._processor: Optional[threading.Thread] = None

        # Preview produced by the processing thread, consumed by the UI.
        self.preview_enabled = True
        self._preview_box = (640, 360)
        self._preview_frame: Optional[np.ndarray] = None
        self._preview_seq = 0
        self.frames_to_vcam = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_listener(self, callback: Callable[[StreamStatus], None]):
        """Status changes are reported from background threads."""
        self._listeners.append(callback)

    @property
    def status(self) -> StreamStatus:
        return self._status

    @property
    def is_active(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def start(self, device: DiscoveredDevice, auto_reconnect: bool = True):
        """Starts streaming from ``device`` in the background."""
        self.stop()
        self._stop_event.clear()
        self._processor = threading.Thread(target=self._process_loop, daemon=True, name="frame-process")
        self._processor.start()
        self._worker = threading.Thread(
            target=self._run, args=(device, auto_reconnect), daemon=True, name="stream-worker"
        )
        self._worker.start()

    def stop(self):
        """Stops streaming and releases the virtual camera."""
        self._stop_event.set()
        self._frame_ready.set()
        receiver = self._receiver
        if receiver:
            receiver.disconnect()
        for thread in (self._worker, self._processor):
            if thread and thread.is_alive() and thread is not threading.current_thread():
                thread.join(timeout=3)
        self._worker = None
        self._processor = None
        self._receiver = None
        if self._vcam:
            self._vcam.stop()
            self._vcam = None
        with self._frame_lock:
            self._pending_frame = None
            self._preview_frame = None
        if self._status.state != StreamState.IDLE:
            self._set_status(StreamState.IDLE, "Disconnected")

    def set_preview(self, enabled: bool, box_width: int = 640, box_height: int = 360):
        self.preview_enabled = enabled
        self._preview_box = (max(1, box_width), max(1, box_height))
        if not enabled:
            with self._frame_lock:
                self._preview_frame = None

    def get_preview_frame(self, last_seq: int) -> Tuple[Optional[np.ndarray], int]:
        """Returns (frame, seq) if a newer preview than ``last_seq`` exists, else (None, last_seq)."""
        with self._frame_lock:
            if self._preview_frame is None or self._preview_seq == last_seq:
                return None, last_seq
            return self._preview_frame, self._preview_seq

    def stats(self) -> Optional[ReceiverStats]:
        receiver = self._receiver
        if receiver and receiver.is_connected():
            return receiver.get_stats()
        return None

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _set_status(self, state: StreamState, message: str = "", device: Optional[DiscoveredDevice] = None):
        with self._lock:
            self._status = StreamStatus(state, message, device or self._status.device)
            status = self._status
        for callback in list(self._listeners):
            try:
                callback(status)
            except Exception as e:
                print(f"Error in status listener: {e}")

    def _ensure_vcam(self):
        if self._vcam is not None:
            return
        vcam = self._vcam_factory(width=self.vcam_size[0], height=self.vcam_size[1], fps=self.vcam_fps)
        if vcam.start():
            self._vcam = vcam
            self.vcam_error = None
            self.vcam_device = vcam.device_name
        else:
            # Keep going: the preview still works and tells the user what is missing.
            self.vcam_error = vcam.last_error or "virtual camera not available"

    def _run(self, device: DiscoveredDevice, auto_reconnect: bool):
        attempt = 0
        ever_connected = False
        self._set_status(StreamState.CONNECTING, f"Connecting to {device.name}…", device)

        while not self._stop_event.is_set():
            # Retried on every attempt: the camera may be registered while VanCamera is running.
            self._ensure_vcam()
            error = self._connect_once(device)
            if error is None:
                attempt = 0
                ever_connected = True
                reason = self._wait_while_streaming()
                if self._stop_event.is_set():
                    break
                error = reason

            if not auto_reconnect:
                self._set_status(StreamState.ERROR, error, device)
                break

            delay = self.RECONNECT_DELAYS_S[min(attempt, len(self.RECONNECT_DELAYS_S) - 1)]
            attempt += 1
            prefix = "Connection lost" if ever_connected else "Waiting for the phone"
            self._set_status(StreamState.RECONNECTING, f"{prefix}: {error}. Retrying…", device)
            if self._stop_event.wait(delay):
                break

    def _connect_once(self, device: DiscoveredDevice) -> Optional[str]:
        """Returns None on success, or an error message."""
        if device.type == "usb":
            if not self._port_forwarder(local_port=device.port, remote_port=device.port, serial=device.serial):
                return "could not set up the USB (adb) tunnel"

        receiver = self._receiver_factory(device.address, device.port, self.cert_handler)
        receiver.set_frame_callback(self._on_frame)
        self._disconnected.clear()
        self._disconnect_reason = ""

        def on_disconnect(reason: str):
            self._disconnect_reason = reason
            self._disconnected.set()

        receiver.set_disconnect_callback(on_disconnect)
        if self._stop_event.is_set() or not receiver.connect():
            return receiver.last_error or "connection failed"
        self._receiver = receiver
        receiver.start_receiving()
        receiver.get_stats()  # reset rate counters
        self._set_status(StreamState.STREAMING, f"Connected to {device.name}", device)
        return None

    def _wait_while_streaming(self) -> str:
        receiver = self._receiver
        if receiver is None:
            return "connection failed"
        while not self._stop_event.is_set():
            if self._disconnected.wait(0.25) or not receiver.is_running:
                break
        receiver.disconnect()
        return self._disconnect_reason or "connection closed"

    # ------------------------------------------------------------------
    # Frame processing
    # ------------------------------------------------------------------

    def _on_frame(self, frame: np.ndarray, orientation_degrees: int, is_back_camera: bool):
        """Receive thread: keep only the newest frame and return immediately."""
        with self._frame_lock:
            self._pending_frame = (frame, orientation_degrees, is_back_camera)
        self._frame_ready.set()

    def _process_loop(self):
        while not self._stop_event.is_set():
            if not self._frame_ready.wait(0.5):
                continue
            self._frame_ready.clear()
            with self._frame_lock:
                item = self._pending_frame
                self._pending_frame = None
            if item is None:
                continue
            frame, orientation, is_back = item
            try:
                vcam = self._vcam
                if vcam is not None:
                    # The virtual camera follows the phone's stream size (720p or 1080p preset).
                    long_side, short_side = max(frame.shape[:2]), min(frame.shape[:2])
                    if (vcam.width, vcam.height) != (long_side, short_side):
                        vcam.set_size(long_side, short_side)
                    vcam.send_frame(frame_transform.for_virtual_camera(frame, orientation, is_back))
                    self.frames_to_vcam += 1
                if self.preview_enabled:
                    box_w, box_h = self._preview_box
                    preview = frame_transform.preview_frame(frame, orientation, is_back, box_w, box_h)
                    with self._frame_lock:
                        self._preview_frame = preview
                        self._preview_seq += 1
            except Exception as e:
                print(f"Frame processing error: {e}")
