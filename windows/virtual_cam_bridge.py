"""
Bridge that sends video frames to the virtual camera (the "VanCamera" Unity Capture device
registered by the installer, or OBS Studio's virtual camera)
"""
from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np

import frame_transform

try:
    import pyvirtualcam
    from pyvirtualcam import PixelFormat
    HAS_PYVIRTUALCAM = True
except ImportError:  # pragma: no cover - depends on the platform
    pyvirtualcam = None
    PixelFormat = None
    HAS_PYVIRTUALCAM = False


class VirtualCamBridge:
    """Bridge between video receiver and virtual camera.

    Frames are composed into a canvas by ``send_frame`` and pushed to the device by a pump thread
    at twice the incoming frame rate. Unity Capture only takes a frame when the reading app asks
    for one and drops the rest, so a sender running at exactly 30 fps loses every other frame
    (measured: 15 fps in Meet/Discord); sending at 60 Hz delivers the full 30 fps.
    """

    SEND_RATE_MULTIPLIER = 2
    MAX_SEND_RATE = 120

    def __init__(self, width: int = 1280, height: int = 720, fps: int = 30):
        self.width = width
        self.height = height
        self.fps = fps
        self.camera = None
        self.is_running = False
        self.last_error: Optional[str] = None
        self.device_name: Optional[str] = None

        # Canvas for letterboxing (reused each frame); guarded by _lock with the camera.
        self._lock = threading.Lock()
        self._canvas: Optional[np.ndarray] = None
        self._last_frame_size: tuple = (0, 0)
        self._cached_scale_params: Optional[tuple] = None
        self._stop_pump = threading.Event()
        self._pump: Optional[threading.Thread] = None
        # Smoothed interval between incoming frames: a 60 fps phone needs a 120 Hz pump.
        self._input_interval = 1.0 / fps
        self._last_input: Optional[float] = None

    def start(self) -> bool:
        """
        Starts the virtual camera

        Returns:
            True if started successfully (``last_error`` explains failures)
        """
        if self.is_running:
            return True
        if not HAS_PYVIRTUALCAM:
            self.last_error = "pyvirtualcam is not installed"
            return False
        try:
            self._open_camera()
        except Exception as e:
            self.last_error = str(e)
            print(f"Error starting virtual camera: {e}")
            return False

        self.is_running = True
        self._stop_pump.clear()
        self._pump = threading.Thread(target=self._pump_loop, name="vancamera-vcam", daemon=True)
        self._pump.start()
        print(f"Virtual camera started: {self.width}x{self.height} @ {self.fps}fps ({self.device_name})")
        return True

    def _open_camera(self):
        """Opens the device at the current size; the caller holds the lock or owns the bridge."""
        self.camera = pyvirtualcam.Camera(
            width=self.width,
            height=self.height,
            fps=self.fps,
            # Use RGB format - our decoder produces RGB frames
            fmt=PixelFormat.RGB
        )
        self.device_name = getattr(self.camera, "device", None)
        # Black frame until video arrives.
        self._canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        self._last_frame_size = (0, 0)

    def set_size(self, width: int, height: int) -> bool:
        """Reopens the device at a new size (the phone switched between 720p and 1080p)."""
        if (width, height) == (self.width, self.height):
            return True
        with self._lock:
            self.width, self.height = width, height
            if not self.is_running:
                return True
            try:
                self.camera.close()
            except Exception:
                pass
            try:
                self._open_camera()
                print(f"Virtual camera resized to {width}x{height}")
                return True
            except Exception as e:
                self.last_error = str(e)
                self.camera = None
                self._canvas = None
                return False

    def _pump_interval(self) -> float:
        rate = self.SEND_RATE_MULTIPLIER / self._input_interval
        return 1.0 / min(max(rate, self.SEND_RATE_MULTIPLIER * self.fps), self.MAX_SEND_RATE)

    def _pump_loop(self):
        next_send = time.perf_counter()
        while not self._stop_pump.is_set():
            interval = self._pump_interval()
            # time.sleep, not Event.wait: on Windows Event.wait rounds up to the ~15.6 ms system
            # tick (pumping at ~32 Hz), while time.sleep uses a high-resolution timer.
            next_send = max(next_send + interval, time.perf_counter())
            time.sleep(max(0.0, next_send - time.perf_counter()))
            with self._lock:
                if self.camera is None or self._canvas is None:
                    continue
                try:
                    self.camera.send(self._canvas)
                except Exception as e:
                    print(f"Error sending frame: {e}")

    def send_frame(self, frame: np.ndarray):
        """
        Sets the frame shown by the virtual camera, letterboxed to the camera size.

        Args:
            frame: Frame as numpy array (RGB)
        """
        if not self.is_running:
            return

        now = time.perf_counter()
        if self._last_input is not None:
            # Ignore gaps (reconnects, dropped frames) so they don't slow the pump down.
            gap = min(now - self._last_input, 1.0 / 15)
            self._input_interval += 0.1 * (gap - self._input_interval)
        self._last_input = now

        frame_h, frame_w = frame.shape[:2]
        with self._lock:
            if self._canvas is None:
                return
            if frame_h == self.height and frame_w == self.width:
                self._canvas[:] = frame
                return

            # Recompute the letterbox only when the frame size (orientation) changes.
            if (frame_h, frame_w) != self._last_frame_size:
                self._last_frame_size = (frame_h, frame_w)
                new_w, new_h = frame_transform.fit_size(frame_w, frame_h, self.width, self.height)
                paste_x = (self.width - new_w) // 2
                paste_y = (self.height - new_h) // 2
                self._cached_scale_params = (new_w, new_h, paste_x, paste_y)
                self._canvas.fill(0)  # clear old borders

            new_w, new_h, paste_x, paste_y = self._cached_scale_params
            # Bilinear resize (OpenCV): much better looking than nearest-neighbour and still ~1 ms.
            resized = frame_transform.resize(frame, new_w, new_h)
            self._canvas[paste_y:paste_y + new_h, paste_x:paste_x + new_w] = resized

    def stop(self):
        """Stops the virtual camera"""
        self._stop_pump.set()
        if self._pump is not None and self._pump is not threading.current_thread():
            self._pump.join(timeout=1)
        self._pump = None
        with self._lock:
            if self.camera:
                try:
                    self.camera.close()
                except Exception:
                    pass
                self.camera = None
            self.is_running = False
            self._canvas = None
            self._cached_scale_params = None
        print("Virtual camera stopped")

    def is_active(self) -> bool:
        """Checks if the virtual camera is active"""
        return self.is_running and self.camera is not None
