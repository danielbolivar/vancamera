"""
Frame orientation handling for VanCamera.

The phone always sends landscape sensor frames plus two flags (see docs/PROTOCOL.md):
the device orientation (0/90/180/270) and whether the back camera is in use. These helpers turn
a decoded frame into what the local preview and the virtual camera should show.

The transformations are unchanged from the original UI code; they were moved here so they can be
unit tested and reused off the UI thread.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:  # pragma: no cover - OpenCV is optional
    HAS_CV2 = False


def _rotate_front_camera(frame: np.ndarray, orientation_degrees: int) -> np.ndarray:
    """Standard rotation for front camera."""
    if orientation_degrees == 90:
        return np.rot90(frame, k=1)
    if orientation_degrees == 180:
        return np.rot90(frame, k=2)
    if orientation_degrees == 270:
        return np.rot90(frame, k=3)
    return frame


def for_preview(frame: np.ndarray, orientation_degrees: int, is_back_camera: bool) -> np.ndarray:
    """Frame as shown in the app's preview (front camera mirrored like a selfie view)."""
    if is_back_camera:
        if orientation_degrees == 90:
            return np.rot90(frame, k=3)
        if orientation_degrees == 180:
            return np.rot90(frame, k=2)
        if orientation_degrees == 270:
            return np.rot90(frame, k=1)
        return frame
    return np.fliplr(_rotate_front_camera(frame, orientation_degrees))


def for_virtual_camera(frame: np.ndarray, orientation_degrees: int, is_back_camera: bool) -> np.ndarray:
    """Frame as sent to the virtual camera (video-call apps mirror the self view themselves)."""
    if is_back_camera:
        if orientation_degrees == 90:
            return np.fliplr(np.rot90(frame, k=3))
        if orientation_degrees == 270:
            return np.fliplr(np.rot90(frame, k=1))
        # Both landscape orientations only need a horizontal flip.
        return np.fliplr(frame)
    return _rotate_front_camera(frame, orientation_degrees)


def rotated_size(width: int, height: int, orientation_degrees: int) -> Tuple[int, int]:
    """Size of a width x height frame after the orientation is applied."""
    if orientation_degrees in (90, 270):
        return height, width
    return width, height


def fit_size(width: int, height: int, box_width: int, box_height: int) -> Tuple[int, int]:
    """Largest size with the same aspect ratio as width x height that fits in the box."""
    if width <= 0 or height <= 0 or box_width <= 0 or box_height <= 0:
        return max(1, box_width), max(1, box_height)
    scale = min(box_width / width, box_height / height)
    return max(1, int(width * scale)), max(1, int(height * scale))


def resize(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    """Resizes an RGB frame (bilinear with OpenCV, nearest-neighbour fallback)."""
    h, w = frame.shape[:2]
    if (w, h) == (width, height):
        return frame
    if HAS_CV2:
        interpolation = cv2.INTER_AREA if width < w else cv2.INTER_LINEAR
        return cv2.resize(np.ascontiguousarray(frame), (width, height), interpolation=interpolation)
    ys = (np.arange(height) * h // height).astype(np.intp)
    xs = (np.arange(width) * w // width).astype(np.intp)
    return frame[ys[:, None], xs]


def preview_frame(frame: np.ndarray, orientation_degrees: int, is_back_camera: bool,
                  box_width: int, box_height: int) -> np.ndarray:
    """
    Downscales first and rotates afterwards: rotating a 1280x720 frame just to shrink it to a
    small preview wastes CPU.
    """
    h, w = frame.shape[:2]
    out_w, out_h = rotated_size(w, h, orientation_degrees)
    target_w, target_h = fit_size(out_w, out_h, box_width, box_height)
    if (target_w, target_h) != (out_w, out_h):
        pre_w, pre_h = rotated_size(target_w, target_h, orientation_degrees)
        frame = resize(frame, pre_w, pre_h)
    return np.ascontiguousarray(for_preview(frame, orientation_degrees, is_back_camera))
