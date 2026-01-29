"""
Bridge to inject video frames into OBS-VirtualCam
"""
import numpy as np
from typing import Optional
import pyvirtualcam
from pyvirtualcam import PixelFormat

# Try to use OpenCV for faster resize (falls back to numpy if not available)
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


class VirtualCamBridge:
    """Bridge between video receiver and virtual camera"""

    def __init__(self, width: int = 1280, height: int = 720, fps: int = 30):
        self.width = width
        self.height = height
        self.fps = fps
        self.camera: Optional[pyvirtualcam.Camera] = None
        self.is_running = False

        # Pre-allocated canvas for letterboxing (reused each frame)
        self._canvas: Optional[np.ndarray] = None
        self._last_frame_size: tuple = (0, 0)
        self._cached_scale_params: Optional[tuple] = None

    def start(self) -> bool:
        """
        Starts the virtual camera

        Returns:
            True if started successfully
        """
        try:
            self.camera = pyvirtualcam.Camera(
                width=self.width,
                height=self.height,
                fps=self.fps,
                # Use RGB format - our decoder produces RGB frames
                fmt=PixelFormat.RGB
            )
            self.is_running = True

            # Pre-allocate canvas (black frame)
            self._canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)

            print(f"Virtual camera started: {self.width}x{self.height} @ {self.fps}fps")
            return True
        except Exception as e:
            print(f"Error starting virtual camera: {e}")
            print("Make sure OBS-VirtualCam is installed")
            return False

    def send_frame(self, frame: np.ndarray):
        """
        Sends a frame to the virtual camera.
        Optimized for low latency - minimal processing.

        Args:
            frame: Frame as numpy array (RGB)
        """
        if not self.is_running or not self.camera:
            return

        try:
            # Fast path: if frame matches target size exactly, send directly
            frame_h, frame_w = frame.shape[:2]

            if frame_h == self.height and frame_w == self.width:
                # Ensure contiguous memory for fastest send
                if not frame.flags['C_CONTIGUOUS']:
                    frame = np.ascontiguousarray(frame)
                self.camera.send(frame)
                return

            # Need to resize - use cached parameters if frame size unchanged
            if (frame_h, frame_w) != self._last_frame_size:
                self._last_frame_size = (frame_h, frame_w)
                # Calculate scaling parameters (cache for reuse)
                scale_w = self.width / frame_w
                scale_h = self.height / frame_h
                scale = min(scale_w, scale_h)
                new_w = int(frame_w * scale)
                new_h = int(frame_h * scale)
                paste_x = (self.width - new_w) // 2
                paste_y = (self.height - new_h) // 2
                self._cached_scale_params = (new_w, new_h, paste_x, paste_y)
                # Reset canvas to black
                self._canvas.fill(0)

            new_w, new_h, paste_x, paste_y = self._cached_scale_params

            # Resize using OpenCV (much faster than PIL)
            if HAS_CV2:
                resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_NEAREST)
            else:
                # Fallback: simple numpy resize (lower quality but fast)
                resized = self._fast_resize(frame, new_w, new_h)

            # Place resized frame on canvas (letterboxing)
            self._canvas[paste_y:paste_y+new_h, paste_x:paste_x+new_w] = resized

            # Send the canvas
            self.camera.send(self._canvas)

        except Exception as e:
            print(f"Error sending frame: {e}")

    def _fast_resize(self, frame: np.ndarray, new_w: int, new_h: int) -> np.ndarray:
        """Fast numpy-based resize (nearest neighbor)"""
        h, w = frame.shape[:2]
        y_indices = (np.arange(new_h) * h // new_h).astype(int)
        x_indices = (np.arange(new_w) * w // new_w).astype(int)
        return frame[y_indices[:, None], x_indices]

    def stop(self):
        """Stops the virtual camera"""
        if self.camera:
            try:
                self.camera.close()
            except:
                pass
            self.camera = None

        self.is_running = False
        self._canvas = None
        self._cached_scale_params = None
        print("Virtual camera stopped")

    def is_active(self) -> bool:
        """Checks if the virtual camera is active"""
        return self.is_running and self.camera is not None
