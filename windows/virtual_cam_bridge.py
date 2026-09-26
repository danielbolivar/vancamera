"""
Bridge to inject video frames into OBS-VirtualCam
"""
from __future__ import annotations

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
    """Bridge between video receiver and virtual camera"""

    def __init__(self, width: int = 1280, height: int = 720, fps: int = 30):
        self.width = width
        self.height = height
        self.fps = fps
        self.camera = None
        self.is_running = False
        self.last_error: Optional[str] = None
        self.device_name: Optional[str] = None

        # Pre-allocated canvas for letterboxing (reused each frame)
        self._canvas: Optional[np.ndarray] = None
        self._last_frame_size: tuple = (0, 0)
        self._cached_scale_params: Optional[tuple] = None

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
            self.camera = pyvirtualcam.Camera(
                width=self.width,
                height=self.height,
                fps=self.fps,
                # Use RGB format - our decoder produces RGB frames
                fmt=PixelFormat.RGB
            )
            self.device_name = getattr(self.camera, "device", None)
            self.is_running = True

            # Pre-allocate canvas (black frame) and show it until video arrives.
            self._canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            self._last_frame_size = (0, 0)
            self.camera.send(self._canvas)

            print(f"Virtual camera started: {self.width}x{self.height} @ {self.fps}fps ({self.device_name})")
            return True
        except Exception as e:
            self.last_error = str(e)
            print(f"Error starting virtual camera: {e}")
            print("Make sure OBS-VirtualCam is installed")
            return False

    def send_frame(self, frame: np.ndarray):
        """
        Sends a frame to the virtual camera, letterboxed to the camera size.

        Args:
            frame: Frame as numpy array (RGB)
        """
        if not self.is_running or not self.camera:
            return

        try:
            frame_h, frame_w = frame.shape[:2]

            # Fast path: if frame matches target size exactly, send directly
            if frame_h == self.height and frame_w == self.width:
                self.camera.send(np.ascontiguousarray(frame))
                return

            # Need to resize - use cached parameters if frame size unchanged
            if (frame_h, frame_w) != self._last_frame_size:
                self._last_frame_size = (frame_h, frame_w)
                new_w, new_h = frame_transform.fit_size(frame_w, frame_h, self.width, self.height)
                paste_x = (self.width - new_w) // 2
                paste_y = (self.height - new_h) // 2
                self._cached_scale_params = (new_w, new_h, paste_x, paste_y)
                # Reset canvas to black (orientation changed: clear old borders)
                self._canvas.fill(0)

            new_w, new_h, paste_x, paste_y = self._cached_scale_params

            # Bilinear resize (OpenCV): much better looking than nearest-neighbour and still ~1 ms.
            resized = frame_transform.resize(frame, new_w, new_h)

            # Place resized frame on canvas (letterboxing)
            self._canvas[paste_y:paste_y + new_h, paste_x:paste_x + new_w] = resized

            self.camera.send(self._canvas)

        except Exception as e:
            print(f"Error sending frame: {e}")

    def stop(self):
        """Stops the virtual camera"""
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
